"""
Ingescape utility functions
Shared utilities for Ingescape agent initialization
"""

import time

def start_with_device_fallback(igs, port, devices=None):
    """
    Try to start Ingescape agent with multiple network devices in fallback order.
    
    Args:
        igs: The ingescape module
        port: Port number to use
        devices: List of device names to try (default: ["wlp0s20f3", "Wi-Fi", "A7500_NETGEAR"])
    
    Returns:
        str: Name of the device that successfully started
        
    Raises:
        RuntimeError: If unable to start with any device
    """
    if devices is None:
        devices = ["wlp0s20f3", "Wi-Fi", "A7500_NETGEAR"]
    
    for device in devices:
        print(f"Attempting to start with device: {device}")
        igs.start_with_device(device, port)
        time.sleep(0.5)  # Give it a moment to initialize
        
        # Check if agent actually started
        if igs.is_started():
            print(f"✓ Successfully started with device: {device}")
            return device
        else:
            print(f"✗ Failed to start with device: {device}")
            igs.stop()  # Clean up failed attempt
    
    print(f"ERROR: Could not start with any device. Tried: {', '.join(devices)}")
    raise RuntimeError(f"Failed to start Ingescape agent with any available device")
