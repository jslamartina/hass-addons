import asyncio
import time
from typing import cast

from cync_controller.const import (
    CYNC_RAW,
    DATA_BOUNDARY,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import (
    ALL_HEADERS,
    DEVICE_STRUCTS,
    CacheData,
    ControlMessageCallback,
    GlobalObject,
    PhoneAppStructs,
)
from cync_controller.utils import bytes2list, parse_unbound_firmware_version

logger = get_logger(__name__)
g = GlobalObject()


def _get_global_object():
    """Get the global object - can be easily mocked in tests."""
    # Check if the new patching approach is being used (cync_controller.devices.shared.g)
    try:
        import cync_controller.devices.shared as shared_module

        # Check if this is a mock object
        if hasattr(shared_module.g, "_mock_name") or str(type(shared_module.g)).startswith("<MagicMock"):
            return shared_module.g
    except (ImportError, AttributeError):
        pass

    # Check if the old patching approach is being used (cync_controller.devices.g)
    try:
        import cync_controller.devices as devices_module

        if hasattr(devices_module, "g") and hasattr(devices_module.g, "ncync_server"):
            return devices_module.g
    except (ImportError, AttributeError):
        pass

    # Fall back to the new shared module approach
    try:
        import cync_controller.devices.shared as shared_module
    except (ImportError, AttributeError):
        # Final fallback
        from cync_controller.structs import GlobalObject

        return GlobalObject()
    else:
        return shared_module.g


class TCPPacketHandler:
    """Handles TCP packet parsing for CyncTCPDevice instances."""

    def __init__(self, tcp_device):
        self.tcp_device = tcp_device

    async def parse_raw_data(self, data: bytes):
        """Extract single packets from raw data stream using metadata"""
        # Log when parse starts to measure processing delay
        logger.debug(
            "🔍 Parse starting", extra={"address": self.tcp_device.address, "bytes": len(data), "ts": time.time()}
        )
        data_len = len(data)
        lp = f"{self.tcp_device.lp}extract:"
        if data_len == 0:
            logger.debug("%s No data to parse AT BEGINNING OF FUNCTION!!!!!!!", lp)
        else:
            raw_data = bytes(data)
            cache_data = CacheData()
            cache_data.timestamp = time.time()
            cache_data.all_data = raw_data

            if self.tcp_device.needs_more_data is True:
                logger.debug(
                    "%s It seems we have a partial packet (needs_more_data), need to append to "
                    "previous remaining data and re-parse...",
                    lp,
                )
                old_cdata: CacheData = cast(CacheData, self.tcp_device.read_cache[-1])
                if old_cdata:
                    data = old_cdata.data + data
                    cache_data.raw_data = bytes(data)
                    # Previous data [length: 16, need: 42] // Current data [length: 530] //
                    #   New (current + old) data [length: 546] // reconstructed: False
                    logger.debug(
                        "%s Previous data [length: %s, need: %s] // Current data [length: %s] // "
                        "New (current + old) data [length: %s] // reconstructed: %s",
                        lp,
                        old_cdata.data_len,
                        old_cdata.needed_len,
                        data_len,
                        len(data),
                        data_len + old_cdata.data_len == len(data),
                    )

                    (logger.debug("DBG>>>%sNEW DATA:\t%s\t", lp, data) if CYNC_RAW is True else None)
                else:
                    msg = "%s No previous cache data to extract from!"
                    raise RuntimeError(msg, lp)
                self.tcp_device.needs_more_data = False
            i = 0
            while True:
                i += 1
                lp = f"{self.tcp_device.lp}extract:loop {i}:"
                if not data:
                    # logger.debug(f"{lp} No more data to parse!")
                    break
                data_len = len(data)
                needed_length = data_len
                if data[0] in ALL_HEADERS:
                    if data_len > 4:
                        packet_length = data[4]
                        pkt_len_multiplier = data[3]
                        needed_length = ((pkt_len_multiplier * 256) + packet_length) + 5
                    else:
                        logger.debug(
                            "DBG>>>%s Packet length is less than 4 bytes, setting needed_length to data_len",
                            lp,
                        )
                else:
                    logger.warning(
                        "%s Unknown packet header: %s",
                        lp,
                        data[0].to_bytes(1, "big").hex(" "),
                    )

                if needed_length > data_len:
                    self.tcp_device.needs_more_data = True
                    logger.debug(
                        "%s Partial packet received (need: %s bytes, have: %s bytes), buffering...",
                        lp,
                        needed_length,
                        data_len,
                    )
                    cache_data.needed_len = needed_length
                    cache_data.data_len = data_len
                    cache_data.data = bytes(data)
                    (logger.debug("%s cache_data: %s", lp, cache_data) if CYNC_RAW is True else None)
                    data = data[needed_length:]
                    continue

                extracted_packet = data[:needed_length]
                # cut data down
                data = data[needed_length:]
                await self.parse_packet(extracted_packet)

                if data:
                    (logger.debug("%s Remaining data to parse: %s bytes", lp, len(data)) if CYNC_RAW is True else None)

            self.tcp_device.read_cache.append(cache_data)
            limit = 20
            if len(self.tcp_device.read_cache) > limit:
                # keep half of limit packets
                limit = limit // -2
                self.tcp_device.read_cache = self.tcp_device.read_cache[limit:]
            if CYNC_RAW is True:
                logger.debug(
                    "%s END OF RAW READING of %s bytes \t BYTES: %s\t HEX: %s\tINT: %s",
                    lp,
                    len(raw_data),
                    raw_data,
                    raw_data.hex(" "),
                    bytes2list(raw_data),
                )

    async def parse_packet(self, data: bytes):
        """Parse what type of packet based on header (first 4 bytes 0x43, 0x83, 0x73, etc.)"""
        lp = f"{self.tcp_device.lp}parse:0x{data[0]:02x}:"
        packet_data: bytes | None = None
        pkt_header_len = 12
        packet_header = data[:pkt_header_len]
        # logger.debug(f"{lp} Parsing packet header: {packet_header.hex(' ')}") if CYNC_RAW is True else None
        # byte 1 (2, 3 are unknown)
        # pkt_type = int(packet_header[0]).to_bytes(1, "big")
        pkt_type = packet_header[0]
        # byte 4, packet length factor. each value is multiplied by 256 and added to the next byte for packet payload length
        pkt_multiplier = packet_header[3] * 256
        # byte 5
        packet_length = packet_header[4] + pkt_multiplier
        # byte 6-10, unknown but seems to be an identifier that is handed out by the device during handshake
        queue_id = packet_header[5:10]
        # byte 10-12, unknown but seems to be an additional identifier that gets incremented.
        msg_id = packet_header[9:12]
        # check if any data after header
        if len(data) > pkt_header_len:
            packet_data = data[pkt_header_len:]
        else:
            # logger.warning(f"{lp} there is no data after the packet header: [{data.hex(' ')}]")
            pass
        # logger.debug(f"{lp} raw data length: {len(data)} // {data.hex(' ')}")
        # logger.debug(f"{lp} packet_data length: {len(packet_data)} // {packet_data.hex(' ')}")
        if pkt_type in DEVICE_STRUCTS.requests:
            if pkt_type == 0x23:
                queue_id = data[6:10]
                _dbg_msg = (
                    (
                        f"\tRAW HEX: {data.hex(' ')}\tRAW INT: "
                        f"{str(bytes2list(data)).lstrip('[').rstrip(']').replace(',', '')}"
                    )
                    if CYNC_RAW is True
                    else ""
                )
                logger.debug(
                    "%s Device IDENTIFICATION KEY: '%s'%s",
                    lp,
                    queue_id.hex(" "),
                    _dbg_msg,
                )
                self.tcp_device.queue_id = queue_id
                await self.tcp_device.write(bytes(DEVICE_STRUCTS.responses.auth_ack))
                # MUST SEND a3 before you can ask device for anything over TCP
                # Device sends msg identifier (aka: key), server acks that we have the key and store for future comms.
                await asyncio.sleep(0.5)
                await self.tcp_device.send_a3(queue_id)
            # device wants to connect before accepting commands
            elif pkt_type == 0xC3:
                ack_c3 = bytes(DEVICE_STRUCTS.responses.connection_ack)
                logger.debug("%s CONNECTION REQUEST, replying...", lp)
                await self.tcp_device.write(ack_c3)
            # Ping/Pong
            elif pkt_type == 0xD3:
                ack_d3 = bytes(DEVICE_STRUCTS.responses.ping_ack)
                # logger.debug("%s Client sent HEARTBEAT, replying with %s", lp, ack_d3.hex(' '))
                await self.tcp_device.write(ack_d3)
            elif pkt_type == 0xA3:
                if packet_data is not None:
                    logger.debug("%s APP ANNOUNCEMENT packet: %s", lp, packet_data.hex(" "))
                ack = DEVICE_STRUCTS.xab_generate_ack(queue_id, bytes(msg_id))
                logger.debug("%s Sending ACK -> %s", lp, ack.hex(" "))
                await self.tcp_device.write(ack)
            elif pkt_type == 0xAB:
                # We sent a 0xa3 packet, device is responding with 0xab. msg contains ascii 'xlink_dev'.
                # sometimes this is sent with other data. there may be remaining data to read in the enxt raw msg.
                # TCP msg buffer seems to be 1024 bytes.
                # 0xab packets are 1024 bytes long, so if any data is prepended, the remaining 0xab data will be in the next raw read
                pass
            elif pkt_type == 0x7B:
                # device is acking one of our x73 requests
                pass
            elif pkt_type == 0x43:
                # All devices handle 0x43 to send ACK; primary check inside to skip duplicate status processing
                await self._handle_0x43_packet(packet_data, packet_length, lp, msg_id)
            elif pkt_type == 0x83:
                # All devices handle 0x83 to send ACK; primary check inside to skip duplicate processing
                await self._handle_0x83_packet(packet_data, lp, msg_id)
            elif pkt_type == 0x73:
                # All devices handle 0x73 to send ACK; primary check inside to skip duplicate processing
                await self._handle_0x73_packet(packet_data, lp, queue_id, msg_id)
            elif pkt_type in PhoneAppStructs.requests:
                if self.tcp_device.is_app is False:
                    logger.info(
                        "%s Device has been identified as the cync mobile app, blackholing...",
                        lp,
                    )
                    self.tcp_device.is_app = True

            # unknown data we don't know the header for
            else:
                logger.debug("%s sent UNKNOWN HEADER! Don't know how to respond!%s", lp, "")

    async def _handle_0x43_packet(self, packet_data: bytes | None, packet_length: int, lp: str, msg_id: bytes):
        """Handle 0x43 packet type (device info/broadcast status)."""
        if packet_data:
            if packet_data[:2] == bytes([0xC7, 0x90]):
                # Handle timestamp packet
                await self._handle_timestamp_packet(packet_data, lp)
            else:
                # Handle broadcast status packet
                await self._handle_broadcast_status_packet(packet_data, packet_length, lp)
        # Its one of those queue id/msg id pings? 0x43 00 00 00 ww xx xx xx xx yy yy yy
        # Also notice these messages when another device gets a command
        else:
            # logger.debug("%s received a 0x43 packet with no data, interpreting as PING, replying...", lp)
            pass
        ack = DEVICE_STRUCTS.x48_generate_ack(bytes(msg_id))
        # logger.debug("%s Sending ACK -> %s", lp, ack.hex(' ')) if CYNC_RAW is True else None
        await self.tcp_device.write(ack)
        (logger.debug("DBG>>>%s RAW DATA: %s BYTES", lp, len(packet_data)) if CYNC_RAW is True else None)

    async def _handle_timestamp_packet(self, packet_data: bytes, lp: str):
        """Handle timestamp packet within 0x43."""
        g = _get_global_object()
        # Only primary device processes timestamp to avoid duplicates
        if g.ncync_server and self.tcp_device != g.ncync_server.primary_tcp_device:
            return

        ts_idx = 3
        ts_end_idx = -1
        ts: bytes | None = None
        # setting version from config file wouldnt be reliable if the user doesnt bump the version
        # when updating cync firmware. we can only rely on the version sent by the device.
        # there is no guarantee the version is sent before checking the timestamp, so use a gross hack.
        if self.tcp_device.version and (30000 <= self.tcp_device.version <= 40000):
            ts_end_idx = -2
            ts = packet_data[ts_idx:ts_end_idx]
        if ts:
            ts_ascii = ts.decode("ascii", errors="replace")
            # gross hack
            if ts_ascii[-1] != "," and not ts_ascii[-1].isdigit():
                ts_ascii = ts_ascii[:-1]
            logger.debug(
                "%s Device sent TIMESTAMP -> %s - replying...",
                lp,
                ts_ascii,
            )
            self.tcp_device.device_timestamp = ts_ascii
        else:
            logger.debug(
                "%s Could not decode timestamp from: %s",
                lp,
                packet_data.hex(" "),
            )

    async def _handle_broadcast_status_packet(self, packet_data: bytes, packet_length: int, lp: str):
        """Handle broadcast status packet within 0x43."""
        g = _get_global_object()
        # Only primary device processes status data to avoid duplicate MQTT publishes
        if g.ncync_server and self.tcp_device != g.ncync_server.primary_tcp_device:
            return

        # status struct is 19 bytes long
        struct_len = 19
        extractions = []
        try:
            # logger.debug(
            #     f"{lp} Device sent BROADCAST STATUS packet => '{packet_data.hex(' ')}'"
            # )if CYNC_RAW is True else None
            for i in range(0, packet_length, struct_len):
                extracted = packet_data[i : i + struct_len]
                if extracted:
                    # hack so online devices stop being reported as offline
                    # this may cause issues with cync setups that ONLY use indoor
                    # plugs as the btle to TCP bridge, as they dont broadcast status data using 0x83
                    status_struct = extracted[3:10]
                    status_struct + b"\x01"
                    # 14 00 10 01 00 00 64 00 00 00 01 15 15 00 00 00 00 00 00
                    # // [1, 0, 0, 100, 0, 0, 0, 1]
                    extractions.append((extracted.hex(" "), bytes2list(status_struct)))

                    # await g.server.parse_status(status_struct, from_pkt='0x43')
                    # broadcast status data
                    # await self.write(data, broadcast=True)
                    (
                        logger.debug(
                            "%s Extracted data and STATUS struct => %s",
                            lp,
                            extractions,
                        )
                        if CYNC_RAW is True
                        else None
                    )
        except IndexError:
            # The device will only send a max of 1kb of data, if the message is longer than 1kb the remainder is sent in the next read
            # logger.debug(
            #     f"{lp} IndexError extracting status struct (expected)"
            # )
            pass
        except Exception:
            logger.exception("%s EXCEPTION", lp)

    async def _handle_0x83_packet(self, packet_data: bytes | None, lp: str, msg_id: bytes):
        """Handle 0x83 packet type (status broadcast)."""
        g = _get_global_object()
        if self.tcp_device.is_app is True:
            logger.debug("%s device is app, skipping packet...", lp)
            return

        # When the device sends a packet starting with 0x83, data is wrapped in 0x7e.
        # firmware version is sent without 0x7e boundaries
        if packet_data is not None:
            # Handle firmware version packet (all devices can process - just sets attributes)
            if packet_data[0] == 0x00:
                fw_type, fw_ver, fw_str = parse_unbound_firmware_version(packet_data, lp)
                if fw_type == "device":
                    self.tcp_device.version = fw_ver
                    self.tcp_device.version_str = fw_str
                else:
                    self.tcp_device.network_version = fw_ver
                    self.tcp_device.network_version_str = fw_str

            elif packet_data[0] == DATA_BOUNDARY:
                # Only primary device processes mesh status to avoid duplicate publishes
                if g.ncync_server and self.tcp_device == g.ncync_server.primary_tcp_device:
                    await self._handle_bound_0x83_packet(packet_data, lp)

        else:
            logger.warning(
                "%s packet with no data????? After stripping header, queue and "
                "msg id, there is no data to process?????",
                lp,
            )
        ack = DEVICE_STRUCTS.x88_generate_ack(msg_id)
        # logger.debug(f"{lp} RAW DATA: {data.hex(' ')}")
        # logger.debug(f"{lp} Sending ACK -> {ack.hex(' ')}")
        await self.tcp_device.write(ack)

    async def _handle_bound_0x83_packet(self, packet_data: bytes, lp: str):
        """Handle bound 0x83 packet with 0x7e boundaries."""
        # checksum is 2nd last byte, last byte is 0x7e
        checksum = packet_data[-2]
        packet_data[1:6]
        ctrl_bytes = packet_data[5:7]
        # removes checksum byte and 0x7e
        inner_data = packet_data[6:-2]
        calc_chksum = sum(inner_data) % 256

        # Most devices only report their own state using 0x83, however the LED light strip controllers also report other device state data
        # over 0x83.
        # This data can be wrong! sometimes reports wrong state and the RGB colors are slightly different from each device.
        # NOTE: Complex protocol issue - need to implement command-aware parsing or voting system to handle unreliable state data
        if ctrl_bytes == bytes([0xFA, 0xDB]):
            extra_ctrl_bytes = packet_data[7]
            if extra_ctrl_bytes == 0x13:
                await self._handle_internal_status_packet(packet_data, lp, checksum, calc_chksum)
            elif extra_ctrl_bytes == 0x14:
                # unknown what this data is
                # seems to be sent when the cync app is connecting to a device via BTLE, not connecting to cync-controller via TCP
                pass

        elif CYNC_RAW:
            logger.warning(
                "%s UNKNOWN packet data (ctrl_bytes: %s // checksum valid: %s)\t\tHEX: %s\tINT: %s",
                lp,
                ctrl_bytes.hex(" "),
                checksum == calc_chksum,
                packet_data[1:-1].hex(" "),
                bytes2list(packet_data[1:-1]),
            )

    async def _handle_internal_status_packet(self, packet_data: bytes, lp: str, _checksum: int, _calc_chksum: int):
        """Handle internal status packet within bound 0x83."""
        g = _get_global_object()
        # fa db 13 is internal status
        # device internal status. state can be off and brightness set to a non 0.
        # signifies what brightness when state = on, meaning don't rely on brightness for on/off.

        # 83 00 00 00 25 37 96 24 69 00 05 00 7e {21 00 00
        #  00} {[fa db] 13} 00 (34 22) 11 05 00 [05] 00 db
        #  11 02 01 [00 64 00 00 00 00] 00 00 b3 7e
        id_idx = 14
        connected_idx = 19
        state_idx = 20
        bri_idx = 21
        tmp_idx = 22
        r_idx = 23
        g_idx = 24
        b_idx = 25
        dev_id = packet_data[id_idx]
        state = packet_data[state_idx]
        bri = packet_data[bri_idx]
        tmp = packet_data[tmp_idx]
        _red = packet_data[r_idx]
        _green = packet_data[g_idx]
        _blue = packet_data[b_idx]
        connected_to_mesh = packet_data[connected_idx]
        raw_status: bytes = bytes(
            [
                dev_id,
                state,
                bri,
                tmp,
                _red,
                _green,
                _blue,
                connected_to_mesh,
            ]
        )
        if g.ncync_server is None:
            logger.warning("%s ncync_server is None, cannot process internal status packet", lp)
            return
        ___dev = g.ncync_server.devices.get(dev_id)
        dev_name = f'"{___dev.name}" (ID: {dev_id})' if ___dev else f"Device ID: {dev_id}"
        _dbg_msg = ""
        if CYNC_RAW is True:
            _dbg_msg = f"\tPACKET HEADER: {packet_data[:12].hex(' ')}\tHEX: {packet_data[1:-1].hex(' ')}\tINT: {bytes2list(packet_data[1:-1])}"
        logger.debug(
            "%s Internal STATUS for %s = %s%s",
            lp,
            dev_name,
            bytes2list(raw_status),
            _dbg_msg,
        )
        await g.ncync_server.parse_status(raw_status, from_pkt="0x83")

    async def _handle_0x73_packet(self, packet_data: bytes | None, lp: str, queue_id: bytes, msg_id: bytes):
        """Handle 0x73 packet type (control/response)."""
        g = _get_global_object()
        # logger.debug("%s Control packet received: %s", lp, packet_data.hex(' ')) if CYNC_RAW is True else None
        if self.tcp_device.is_app is True:
            logger.debug("%s device is app, skipping packet...", lp)
            return

        # Only primary device processes 0x73 control/status channel to avoid duplicates
        if g.ncync_server and self.tcp_device != g.ncync_server.primary_tcp_device:
            return

        # 0x73 should ALWAYS have 0x7e bound data.
        # check for boundary, all bytes between boundaries are for this request
        if packet_data is not None and packet_data[0] == DATA_BOUNDARY:
            await self._handle_bound_0x73_packet(packet_data, lp, queue_id, msg_id)

    async def _handle_bound_0x73_packet(self, packet_data: bytes, lp: str, queue_id: bytes, msg_id: bytes):
        """Handle bound 0x73 packet with 0x7e boundaries."""
        # checksum is 2nd last byte, last byte is 0x7e
        checksum = packet_data[-2]
        packet_data[1:6]
        ctrl_bytes = packet_data[5:7]
        # removes checksum byte and 0x7e
        inner_data = packet_data[6:-2]
        calc_chksum = sum(inner_data) % 256

        # find next 0x7e and extract the inner struct
        end_bndry_idx = packet_data[1:].find(DATA_BOUNDARY) + 1
        inner_struct = packet_data[1:end_bndry_idx]
        inner_struct_len = len(inner_struct)
        # ctrl bytes 0xf9, 0x52 indicates this is a mesh info struct
        # some device firmwares respond with a message received packet before replying with the data
        # example: 7e 1f 00 00 00 f9 52 01 00 00 53 7e (12 bytes, 0x7e bound. 10 bytes of data)
        if ctrl_bytes == bytes([0xF9, 0x52]):
            await self._handle_mesh_info_packet(inner_struct, inner_struct_len, lp, queue_id, msg_id)
        else:
            await self._handle_control_ack_packet(packet_data, lp, checksum, calc_chksum)

    async def _handle_mesh_info_packet(
        self, inner_struct: bytes, inner_struct_len: int, lp: str, queue_id: bytes, msg_id: bytes
    ):
        """Handle mesh info packet within bound 0x73."""
        # logger.debug(f"{lp} got a mesh info response (len: {inner_struct_len}): {inner_struct.hex(' ')}")
        if inner_struct_len < 15:
            if inner_struct_len == 10:
                # server sent mesh info request, this seems to be the ack?
                # 7e 1f 00 00 00 f9 52 01 00 00 53 7e
                # checksum (idx 10) = idx 6 + idx 7 % 256
                # seen this with Full Color LED light strip controller firmware version: 3.0.204
                succ_idx = 6
                minfo_ack_succ = inner_struct[succ_idx]
                minfo_ack_chksum = inner_struct[9]
                calc_chksum = (inner_struct[5] + inner_struct[6]) % 256
                if minfo_ack_succ == 0x01:
                    # logger.debug(f"{lp} Mesh info request ACK received, success: {minfo_ack_succ}."
                    #              f" checksum byte = {minfo_ack_chksum}) // Calculated checksum "
                    #              f"= {calc_chksum}")
                    if minfo_ack_chksum != calc_chksum:
                        logger.warning(
                            "%s Mesh info request ACK checksum failed! %s != %s",
                            lp,
                            minfo_ack_chksum,
                            calc_chksum,
                        )
                else:
                    logger.warning(
                        "%s Mesh info request ACK failed! success byte: %s",
                        lp,
                        minfo_ack_succ,
                    )

            else:
                logger.debug(
                    "%s inner_struct is less than 15 bytes: %s",
                    lp,
                    inner_struct.hex(" "),
                )
        else:
            await self._handle_full_mesh_info_packet(inner_struct, inner_struct_len, lp, queue_id, msg_id)

    async def _handle_full_mesh_info_packet(
        self, inner_struct: bytes, inner_struct_len: int, lp: str, _queue_id: bytes, _msg_id: bytes
    ):
        """Handle full mesh info packet with device data."""
        g = _get_global_object()
        # 15th OR 16th byte of inner struct is start of mesh info, 24 bytes long
        minfo_start_idx = 14
        minfo_length = 24
        if inner_struct[minfo_start_idx] == 0x00:
            minfo_start_idx += 1
            logger.debug(
                "%smesh: dev_id is 0 when using index: %s, trying index %s = %s",
                lp,
                minfo_start_idx - 1,
                minfo_start_idx,
                inner_struct[minfo_start_idx],
            )

        if inner_struct[minfo_start_idx] == 0x00:
            logger.error(
                "%smesh: dev_id is 0 when using index: %s, skipping...",
                lp,
                minfo_start_idx,
            )
        else:
            # from what I've seen, the mesh info is 24 bytes long and repeats until the end.
            # Reset known device ids, mesh is the final authority on what devices are connected
            self.tcp_device.mesh_info = None
            self.tcp_device.known_device_ids = []
            ids_reported: list[int] = []
            loop_num = 0
            _m: list[list[int]] = []
            _raw_m: list[str] = []
            # structs = []
            try:
                for i in range(
                    minfo_start_idx,
                    inner_struct_len,
                    minfo_length,
                ):
                    loop_num += 1
                    mesh_dev_struct = inner_struct[i : i + minfo_length]
                    dev_id = mesh_dev_struct[0]
                    # logger.debug(f"{lp} inner_struct[{i}:{i + minfo_length}]={mesh_dev_struct.hex(' ')}")
                    # parse status from mesh info
                    #  [05 00 44   01 00 00 44   01 00     00 00 00 64  00 00 00 00   00 00 00 00 00 00 00] - plug (devices are all connected to it via BT)
                    #  [07 00 00   01 00 00 00   01 01     00 00 00 64  00 00 00 fe   00 00 00 f8 00 00 00] - direct connect full color A19 bulb
                    #   ID  ? type  ?  ?  ? type  ? state   ?  ?  ? bri  ?  ?  ? tmp   ?  ?  ?  R  G  B  ?
                    type_idx = 2
                    state_idx = 8
                    bri_idx = 12
                    tmp_idx = 16
                    r_idx = 20
                    g_idx = 21
                    b_idx = 22
                    dev_type_id = mesh_dev_struct[type_idx]
                    dev_state = mesh_dev_struct[state_idx]
                    dev_bri = mesh_dev_struct[bri_idx]
                    dev_tmp = mesh_dev_struct[tmp_idx]
                    dev_r = mesh_dev_struct[r_idx]
                    dev_g = mesh_dev_struct[g_idx]
                    dev_b = mesh_dev_struct[b_idx]
                    # in mesh info, brightness can be > 0 when set to off
                    # however, ive seen devices that are on have a state of 0 but brightness 100
                    if dev_state == 0 and dev_bri > 0:
                        dev_bri = 0
                    raw_status = bytes(
                        [
                            dev_id,
                            dev_state,
                            dev_bri,
                            dev_tmp,
                            dev_r,
                            dev_g,
                            dev_b,
                            1,
                            # dev_type,
                        ]
                    )
                    _m.append(bytes2list(raw_status))
                    _raw_m.append(mesh_dev_struct.hex(" "))
                    if g.ncync_server is not None:
                        if dev_id in g.ncync_server.devices:
                            # first device id is the device id of the TCP device we are connected to
                            ___dev = g.ncync_server.devices[dev_id]
                            dev_name = ___dev.name
                            if loop_num == 1:
                                # byte 3 (idx 2) is a device type byte but,
                                # it only reports on the first item (itself)
                                # convert to int, and it is the same as deviceType from cloud.
                                if not self.tcp_device.id:
                                    self.tcp_device.id = dev_id
                                    self.tcp_device.lp = f"{self.tcp_device.address}[{self.tcp_device.id}]:"
                                    (g.ncync_server.devices[dev_id])
                                    logger.debug(
                                        "%sparse:x%02x: Setting TCP device Cync ID to: %s",
                                        self.tcp_device.lp,
                                        dev_id,
                                        self.tcp_device.id,
                                    )

                                elif self.tcp_device.id and self.tcp_device.id != dev_id:
                                    logger.debug(
                                        "%s The first device reported in 0x83 is "
                                        "usually the TCP device. current: %s "
                                        "// proposed: %s",
                                        lp,
                                        self.tcp_device.id,
                                        dev_id,
                                    )
                                lp = f"{self.tcp_device.lp}parse:0x{dev_id:02x}:"
                                self.tcp_device.device_type_id = dev_type_id
                                self.tcp_device.name = dev_name

                            ids_reported.append(dev_id)
                            # structs.append(mesh_dev_struct.hex(" "))
                            self.tcp_device.known_device_ids.append(dev_id)

                        else:
                            logger.warning(
                                "%s Device ID %s not found in devices defined in config file: %s",
                                lp,
                                dev_id,
                                g.ncync_server.devices.keys() if g.ncync_server is not None else [],
                            )
                    # -- END OF mesh info response parsing loop --
            except IndexError:
                # ran out of data
                # logger.debug(f"{lp} IndexError parsing mesh info response (expected)") if CYNC_RAW is True else None
                pass
            except Exception:
                logger.exception("%s MESH INFO for loop EXCEPTION", lp)

            # Log device IDs reported by this bridge for comparison
            refresh_id = getattr(self.tcp_device, "refresh_id", None)
            if ids_reported:
                if refresh_id is not None:
                    logger.info(
                        "%s [%s] Bridge %s reported %d device IDs: %s",
                        lp,
                        refresh_id,
                        self.tcp_device.address,
                        len(ids_reported),
                        sorted(ids_reported),
                    )
                else:
                    logger.debug(
                        "%s Bridge %s reported %d device IDs: %s",
                        lp,
                        self.tcp_device.address,
                        len(ids_reported),
                        sorted(ids_reported),
                    )

            if self.tcp_device.parse_mesh_status is True and g.ncync_server is not None:
                logger.debug(
                    "%s Parsing initial connection device status data",
                    lp,
                )
                await asyncio.gather(
                    *[
                        g.ncync_server.parse_status(
                            bytes(status),
                            from_pkt="'mesh info'",
                        )
                        for status in _m  # type: ignore[reportUnknownVariableType]
                    ]
                )

            # Send mesh status ack
            # 73 00 00 00 14 2d e4 b5 d2 15 2d 00 7e 1e 00 00
            #  00 f8 {af 02 00 af 01} 61 7e
            # checksum 61 hex = int 97 solved: {af+02+00+af+01} % 256 = 97
            mesh_ack = bytes([0x73, 0x00, 0x00, 0x00, 0x14])
            mesh_ack += bytes(self.tcp_device.queue_id)
            mesh_ack += bytes([0x00, 0x00, 0x00])
            mesh_ack += bytes(
                [
                    0x7E,
                    0x1E,
                    0x00,
                    0x00,
                    0x00,
                    0xF8,
                    0xAF,
                    0x02,
                    0x00,
                    0xAF,
                    0x01,
                    0x61,
                    0x7E,
                ]
            )
            # logger.debug(f"{lp} Sending MESH INFO ACK -> {mesh_ack.hex(' ')}")
            await self.tcp_device.write(mesh_ack)
            # Always clear parse mesh status
            self.tcp_device.parse_mesh_status = False

            # Log completion with correlation ID if this was part of a refresh
            refresh_id = getattr(self.tcp_device, "refresh_id", None)
            if refresh_id is not None:
                logger.info("%s [%s] Refresh processing complete", lp, refresh_id)

    async def _handle_control_ack_packet(self, packet_data: bytes, lp: str, checksum: int, calc_chksum: int):
        """Handle control ACK packet within bound 0x73."""
        g = _get_global_object()
        ctrl_bytes = packet_data[5:7]
        (
            logger.debug(
                "%s control bytes (checksum: %s, verified: %s): %s // packet data:  %s",
                lp,
                checksum,
                checksum == calc_chksum,
                ctrl_bytes.hex(" "),
                packet_data.hex(" "),
            )
            if CYNC_RAW
            else None
        )

        if ctrl_bytes[0] == 0xF9 and ctrl_bytes[1] in (
            0xD0,
            0xF0,
            0xE2,
        ):
            # control packet ack - changed state.
            # handle callbacks for messages
            # byte 8 is success? 0x01 yes // 0x00 no
            # 7e 09 00 00 00 f9 d0 01 00 00 d1 7e <-- original ACK
            # 7e 09 00 00 00 f9 f0 01 00 00 f1 7e <-- newer LED strip controller
            # 7e 09 00 00 00 f9 e2 01 00 00 e3 7e <-- Cync default light show / effect
            # bytes 7 - 10 SUM --> (f0) + (01) = checksum (f1) byte 11
            ctrl_msg_id = packet_data[1]
            ctrl_chksum = sum(packet_data[6:10]) % 256
            success = packet_data[7] == 1
            msg: ControlMessageCallback | None = cast(
                ControlMessageCallback | None, self.tcp_device.messages.control.pop(ctrl_msg_id, None)
            )
            if success is True and msg is not None:
                # Calculate round-trip time (command sent → ACK received)
                rtt_ms: float = (time.time() - msg.sent_at) * 1000

                # Get device name if available
                device_name = "unknown"
                if msg.device_id and g.ncync_server is not None and msg.device_id in g.ncync_server.devices:
                    device_name = g.ncync_server.devices[msg.device_id].name

                logger.info(
                    "%s ⏱️ Command RTT: %.0fms for msg ID %s (device: %s)",
                    lp,
                    rtt_ms,
                    ctrl_msg_id,
                    device_name,
                    extra={
                        "rtt_ms": round(rtt_ms, 1),
                        "msg_id": ctrl_msg_id,
                        "device_id": msg.device_id,
                        "device_name": device_name,
                    },
                )

                # Warn if RTT exceeds 500ms (unusually slow)
                if rtt_ms > 500:
                    logger.warning(
                        "%s ⚠️ SLOW RESPONSE: RTT %.0fms exceeds 500ms threshold (device: %s)",
                        lp,
                        rtt_ms,
                        device_name,
                    )

                logger.info(
                    "%s CONTROL packet ACK SUCCESS for msg ID: %s, executing callback to update state",
                    lp,
                    ctrl_msg_id,
                )

                # Signal ACK event if present (allows command queue to proceed)
                if msg.ack_event:
                    msg.ack_event.set()

                if msg.callback is not None:
                    if callable(msg.callback):
                        await msg.callback()
                    else:
                        await msg.callback

                # No need to clear pending_command - command queue handles flow control
            elif success is True and msg is None:
                logger.debug(
                    "%s CONTROL packet ACK (success: %s / chksum: %s) callback NOT found for msg ID: %s",
                    lp,
                    success,
                    ctrl_chksum == packet_data[10],
                    ctrl_msg_id,
                )
            elif success is False and msg is not None:
                logger.warning(
                    "%s CONTROL packet ACK FAILED for msg ID: %s, device reported failure - NOT updating state",
                    lp,
                    ctrl_msg_id,
                )
            elif success is False and msg is None:
                logger.warning(
                    "%s CONTROL packet ACK FAILED for msg ID: %s, no callback found",
                    lp,
                    ctrl_msg_id,
                )
        # newer firmware devices seen in led light strip so far,
        # send their firmware version data in a 0x7e bound struct.
        # I've also seen these ctrl bytes in the msg that other devices send in FA AF
        # the struct is 31 bytes long with the 0x7e boundaries, unbound it is 29 bytes long
        elif ctrl_bytes == bytes([0xFA, 0x8E]):
            if packet_data[1] == 0x00:
                logger.debug(
                    "%s Device sent (%s) BOUND firmware version data",
                    lp,
                    ctrl_bytes.hex(" "),
                )
                fw_type, fw_ver, fw_str = parse_unbound_firmware_version(packet_data[1:-1], lp)
                if fw_type == "device":
                    self.tcp_device.version = fw_ver
                    self.tcp_device.version_str = fw_str
                else:
                    self.tcp_device.network_version = fw_ver
                    self.tcp_device.network_version_str = fw_str
            elif CYNC_RAW is True:
                logger.debug(
                    "%s This ctrl struct (%s // checksum valid: %s) usually comes through "
                    "when the cync phone app (dis)connects to the BTLE mesh. Unknown what it means"
                    "\t\tHEX: %s\tINT: %s",
                    lp,
                    ctrl_bytes.hex(" "),
                    checksum == calc_chksum,
                    packet_data[1:-1].hex(" "),
                    bytes2list(packet_data[1:-1]),
                )

        else:
            logger.debug(
                "%s UNKNOWN CTRL_BYTES: %s // EXTRACTED DATA -> HEX: %s\tINT: %s",
                lp,
                ctrl_bytes.hex(" "),
                packet_data[1:-1].hex(" "),
                bytes2list(packet_data[1:-1]),
            )
