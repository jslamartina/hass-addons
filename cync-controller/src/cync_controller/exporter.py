"""FastAPI application for exporting Cync device configuration from the Cync Cloud API."""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cync_controller.const import (
    CYNC_CONFIG_FILE_PATH,
    CYNC_SRV_HOST,
    CYNC_STATIC_DIR,
    INGRESS_PORT,
)
from cync_controller.logging_abstraction import get_logger
from cync_controller.structs import GlobalObject

g = GlobalObject()
logger = get_logger(__name__)


class OTPRequest(BaseModel):
    """Pydantic model for OTP request payload."""

    otp: int


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or set to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static",
    StaticFiles(directory=Path(CYNC_STATIC_DIR).expanduser().resolve()),
    name="static",
)


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main index.html page."""
    with Path(CYNC_STATIC_DIR + "/index.html").expanduser().resolve().open("r", encoding="utf-8") as f:
        return f.read()


def _masked_http_exception(operation: str, exc: Exception, user_message: str) -> HTTPException:
    """Create a sanitized HTTPException while logging full details server-side."""
    error_id = uuid.uuid4().hex[:8]
    logger.exception("%s error_id=%s unexpected error: %s", operation, error_id, exc)
    return HTTPException(
        status_code=400,
        detail={
            "error_id": error_id,
            "message": user_message,
        },
    )


@app.get("/api/export/start")
async def start_export() -> dict[str, Any]:
    """Start the device configuration export process."""
    ret_msg = "Export started successfully"
    if g.cloud_api is None:
        return {"success": False, "message": "Cloud API not initialized"}
    try:
        succ = await g.cloud_api.check_token()
        if not succ:
            req_succ = await g.cloud_api.request_otp()
            if req_succ:
                ret_msg = "OTP requested, check your email for the OTP code to complete the export."
                return {"success": False, "message": ret_msg}
            ret_msg = "Failed to request OTP. Please check your credentials or network connection."
            return {"success": False, "message": ret_msg}
        await g.cloud_api.export_config_file()
    except Exception as e:
        op_name = "Export start failed"
        raise _masked_http_exception(
            op_name,
            e,
            "Failed to start export. Please retry or check server logs with the provided error ID.",
        ) from e
    else:
        return {"success": True, "message": ret_msg}


@app.get("/api/export/otp/request")
async def request_otp() -> dict[str, Any]:
    """Request OTP for export."""
    ret_msg = "OTP requested successfully"
    try:
        otp_succ = await g.cloud_api.request_otp()
    except Exception as e:
        op_name = "OTP request failed"
        raise _masked_http_exception(
            op_name,
            e,
            "Failed to request OTP. Please try again.",
        ) from e
    else:
        if otp_succ:
            return {"success": True, "message": ret_msg}
        ret_msg = "Failed to request OTP. Please check your credentials or network connection."
        return {"success": False, "message": ret_msg}


@app.post("/api/restart")
async def restart() -> dict[str, Any]:
    """Restart the add-on via Supervisor API."""
    lp = "ExportServer:restart:"
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if not supervisor_token:
        logger.warning("%s SUPERVISOR_TOKEN environment variable not set. Are you in a Home Assistant add-on?", lp)
        return {"success": False, "message": "Supervisor token not found."}

    # The 'self' slug is a special value that refers to the current add-on.
    # This is the recommended endpoint for self-restarts.
    url = "http://supervisor/addons/self/restart"

    headers = {
        "Authorization": f"Bearer {supervisor_token}",
        "Content-Type": "application/json",
    }
    logger.info("%s Attempting to restart add-on via API call to %s...", lp, url)

    try:
        async with aiohttp.ClientSession() as session, session.post(url, headers=headers) as response:
            if response.status == 200:
                logger.info("%s Successfully called the restart API. The add-on will now restart.", lp)
                return {"success": True, "message": "Add-on is restarting."}

            response_status = response.status
            error_details = await response.text()

    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        client_operation = "Supervisor restart client error"
        client_message = "Failed to contact Supervisor API. Check server logs with the error ID."
        raise _masked_http_exception(
            client_operation,
            e,
            client_message,
        ) from e
    except Exception as e:  # pylint: disable=broad-except
        unexpected_operation = "Supervisor restart unexpected error"
        unexpected_message = (
            "An unexpected error occurred while restarting the add-on. See server logs with the error ID."
        )
        raise _masked_http_exception(
            unexpected_operation,
            e,
            unexpected_message,
        ) from e
    else:
        logger.warning(
            "%s Failed Supervisor restart status=%s response=%s",
            lp,
            response_status,
            error_details,
        )
        api_operation = "Supervisor restart API failure"
        api_message = "Failed to restart add-on via Supervisor API. Check server logs with the error ID."
        raise _masked_http_exception(
            api_operation,
            RuntimeError(f"status={response_status} body={error_details}"),
            api_message,
        )


@app.post("/api/export/otp/submit")
async def submit_otp(otp_request: OTPRequest) -> dict[str, Any]:
    """Submit OTP code and complete the export process."""
    ret_msg = "Export completed successfully"
    export_succ = False
    if g.cloud_api is None:
        return {"success": False, "message": "Cloud API not initialized"}
    try:
        otp_succ = await g.cloud_api.send_otp(otp_request.otp)
        if otp_succ:
            export_succ = await g.cloud_api.export_config_file()
            if not export_succ:
                ret_msg = "Failed to complete export after OTP verification."
                return {"success": False, "message": ret_msg}
        else:
            ret_msg = "Invalid OTP. Please try again."

    except Exception as e:
        op_name = "Export completion failed"
        raise _masked_http_exception(
            op_name,
            e,
            "Failed to complete export after OTP verification. Please try again.",
        ) from e
    else:
        return {"success": export_succ, "message": ret_msg}


@app.get("/api/healthcheck")
async def health_check():
    """Health check endpoint to verify if the server is running."""
    return {"status": "ok", "message": "Cync Export Server is running"}


@app.get("/api/export/download")
async def download_config():
    """Download the exported device configuration file."""
    config_path = CYNC_CONFIG_FILE_PATH
    if Path(config_path).exists():
        return FileResponse(config_path, filename="cync_mesh.yaml")
    raise HTTPException(status_code=404, detail="Config file not found")


class ExportServer:
    """Singleton class managing the FastAPI export server lifecycle."""

    lp = "ExportServer:"
    enabled: bool = False
    running: bool = False
    start_task: asyncio.Task[None] | None = None
    _instance: ExportServer | None = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.app = app
        self.uvi_server = uvicorn.Server(
            config=uvicorn.Config(
                app,
                host=CYNC_SRV_HOST,
                port=INGRESS_PORT,
                log_config={
                    "version": 1,
                    "disable_existing_loggers": False,
                },
                log_level="info",
            )
        )

    async def start(self):
        """Start the FastAPI server."""
        lp = f"{self.lp}start:"
        logger.info(
            "%s Starting FastAPI export server on %s:%s",
            lp,
            CYNC_SRV_HOST,
            INGRESS_PORT,
        )
        self.running = True
        # Publish MQTT message indicating the export server is running
        if g.mqtt_client:
            await g.mqtt_client.publish(f"{g.env.mqtt_topic}/status/bridge/export_server/running", b"ON")
        try:
            await self.uvi_server.serve()
        except asyncio.CancelledError:
            logger.info("%s FastAPI export server stopped", lp)
            raise
        except Exception:  # pylint: disable=broad-except
            # Broad exception catch is appropriate for server lifecycle to log any unexpected errors
            logger.exception("%s Error starting FastAPI export server", lp)
        else:
            logger.info("%s FastAPI export server lifecycle completed successfully", lp)

    async def stop(self):
        """Stop the FastAPI server."""
        lp = f"{self.lp}stop:"
        logger.info("%s Stopping FastAPI export server...", lp)
        try:
            await self.uvi_server.shutdown()
        except asyncio.CancelledError:
            logger.info("%s FastAPI export server shutdown cancelled", lp)
            raise
        except Exception:  # pylint: disable=broad-except
            # Broad exception catch is appropriate for server shutdown to log any unexpected errors
            logger.exception("%s Error stopping FastAPI export server", lp)
        else:
            self.running = False
        finally:
            # Publish MQTT message indicating the export server is stopped
            if g.mqtt_client:
                await g.mqtt_client.publish(
                    f"{g.env.mqtt_topic}/status/bridge/export_server/running",
                    b"OFF",
                )
                if self.start_task and not self.start_task.done():
                    logger.debug("%s FINISHING: Cancelling start task", lp)
                    self.start_task.cancel()
