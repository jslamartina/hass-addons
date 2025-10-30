"""
Cync device classes and TCP communication handlers.

This module provides backward compatibility by re-exporting classes from the
new modular structure. The actual implementations are now in the devices/
package for better organization and maintainability.
"""

# Re-export public classes for backward compatibility
from .devices.base_device import CyncDevice
from .devices.group import CyncGroup
from .devices.tcp_device import CyncTCPDevice

__all__ = ["CyncDevice", "CyncGroup", "CyncTCPDevice"]
