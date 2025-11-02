# Integration Test Network Communication Flow

This diagram illustrates the actual TCP network communication that occurs during the python-rebuild-tcp-comm integration tests.

## Network Architecture

```mermaid
graph TB
    subgraph TestProc["Test Process - localhost"]
        TestCase[Test Case]
        TCPConnection[TCPConnection Client]
        MockServer[MockTCPServer]
    end

    subgraph OSNet["OS Network Stack"]
        Socket1[Client Socket]
        Socket2[Server Socket]
        Loopback[Loopback 127.0.0.1]
    end

    TestCase -->|Call toggle| TCPConnection
    TCPConnection -->|Return result| TestCase
    TestCase -.->|Start fixture| MockServer

    TCPConnection -->|open_connection| Socket1
    MockServer -->|start_server| Socket2

    Socket1 <-->|TCP Handshake| Socket2
    Socket1 -->|Send Packet| Loopback
    Loopback -->|Route| Socket2
    Socket2 -->|Send Response| Socket1

    style Loopback fill:#e1f5ff
    style Socket1 fill:#fff4e6
    style Socket2 fill:#fff4e6
```

## Sequence Diagram - Happy Path

```mermaid
sequenceDiagram
    participant Test as Test Case
    participant Client as TCPConnection
    participant OS as OS Network Stack
    participant Server as MockTCPServer

    Note over Test,Server: Setup Phase
    Test->>Server: Start server (pytest fixture)
    Server->>OS: bind(127.0.0.1, port)
    Server->>OS: listen()
    OS-->>Server: Server socket ready

    Note over Test,Server: Test Execution Phase
    Test->>Client: toggle_device_with_retry()
    Client->>OS: socket.connect(127.0.0.1, port)
    OS->>Server: TCP SYN
    Server->>OS: TCP SYN-ACK
    OS->>Client: TCP ACK
    Note over Client,Server: TCP Connection Established

    Note over Test,Server: Packet Transmission
    Client->>Client: Build packet:<br/>Magic: 0xF00D<br/>Version: 0x01<br/>Length: N bytes<br/>Payload: JSON
    Client->>OS: write(packet_bytes)
    OS->>Server: TCP segment(s) with data
    Server->>Server: read(7) # Read header
    Server->>Server: read(N) # Read payload
    Server->>Server: Parse JSON payload
    Server->>Server: Store packet in received_packets[]

    Note over Test,Server: Response Phase
    Server->>OS: write(b"ACK")
    OS->>Client: TCP segment with "ACK"
    Client->>Client: recv(1024)
    Client-->>Test: Return True (success)

    Note over Test,Server: Teardown Phase
    Test->>Client: close()
    Client->>OS: socket.close()
    OS->>Server: TCP FIN
    Test->>Server: stop() (fixture cleanup)
    Server->>OS: server.close()
```

## Packet Format

```mermaid
graph LR
    subgraph WireFormat["Wire Format - Bytes on Network"]
        Magic["Magic Bytes: 0xF0 0x0D (2 bytes)"]
        Version["Version: 0x01 (1 byte)"]
        Length["Payload Length: Big-endian (4 bytes)"]
        Payload["JSON Payload: UTF-8 (N bytes)"]

        Magic --> Version --> Length --> Payload
    end

    subgraph JSONStruct["JSON Payload Structure"]
        JSON["opcode: 'toggle'<br/>device_id: 'TEST_xxx'<br/>msg_id: 'uuid'<br/>state: true/false"]
    end

    Payload -.->|decode UTF-8| JSON

    style Magic fill:#ff6b6b
    style Version fill:#4ecdc4
    style Length fill:#ffe66d
    style Payload fill:#95e1d3
```

## Test Scenarios and Network Behavior

```mermaid
graph TD
    Start[Test Start] --> Connect{TCP Connect}

    Connect -->|Success| SendPacket[Send Toggle Packet]
    Connect -->|Timeout| Retry1{Retry?}
    Connect -->|Refused| Retry1

    SendPacket --> WaitResponse{Wait for Response}

    WaitResponse -->|ACK received| Success[Test Pass]
    WaitResponse -->|Timeout| Retry2{Retry?}
    WaitResponse -->|Connection closed| Retry2

    Retry1 -->|Yes| Connect
    Retry1 -->|No| Fail[Test Fail]

    Retry2 -->|Yes| Connect
    Retry2 -->|No| Fail

    style Success fill:#51cf66
    style Fail fill:#ff6b6b
```

## MockTCPServer Response Modes

The MockTCPServer can simulate different network conditions:

```mermaid
stateDiagram-v2
    [*] --> AcceptConnection: Client connects

    state ResponseMode <<choice>>
    AcceptConnection --> ResponseMode: Read packet

    ResponseMode --> SUCCESS: mode=SUCCESS
    ResponseMode --> DELAY: mode=DELAY
    ResponseMode --> TIMEOUT: mode=TIMEOUT
    ResponseMode --> DISCONNECT: mode=DISCONNECT
    ResponseMode --> REJECT: mode=REJECT

    SUCCESS --> SendACK: Immediate
    DELAY --> Sleep: Wait N seconds
    Sleep --> SendACK
    TIMEOUT --> Wait: Never respond
    DISCONNECT --> Close: Immediate disconnect
    REJECT --> Close: Reject before read

    SendACK --> [*]: Close gracefully
    Wait --> [*]: Client times out
    Close --> [*]: Connection closed

    note right of SUCCESS
        Real TCP communication
        with controlled behavior
    end note
```

## Key Characteristics

1. **Real TCP Sockets**: Uses actual OS network stack via `asyncio.open_connection()` and `asyncio.start_server()`
2. **Loopback Communication**: All traffic stays on `127.0.0.1` (localhost)
3. **Actual Packet Serialization**: Bytes are marshalled, sent over wire, and unmarshalled
4. **Real Network Errors**: Timeouts, connection refused, disconnections are genuine OS-level events
5. **Performance Measurement**: Latency includes actual TCP overhead, serialization, and OS scheduling
