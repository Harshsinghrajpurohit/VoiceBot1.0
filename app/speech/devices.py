"""Laptop speakerphone devices. A headset is optional."""

import ctypes
import uuid
from ctypes import (
    POINTER,
    WINFUNCTYPE,
    Structure,
    byref,
    c_float,
    c_ubyte,
    c_uint,
    c_ushort,
    c_void_p,
)


class _GUID(Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


def _guid(text: str) -> _GUID:
    value = uuid.UUID(text)
    return _GUID(
        value.time_low,
        value.time_mid,
        value.time_hi_version,
        (c_ubyte * 8).from_buffer_copy(value.bytes[8:]),
    )


def unmute_microphone() -> bool:
    """Turn the default microphone on. Returns True when it had been muted."""
    try:
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        enumerator = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(_guid("BCDE0395-E52F-467C-8E3D-C4579291692E")),
            None,
            1,
            byref(_guid("A95664D2-9614-4F35-A746-DE8DB63617E6")),
            byref(enumerator),
        )
        if hr != 0:
            return False
        get_default = WINFUNCTYPE(
            ctypes.c_long, c_void_p, c_uint, c_uint, POINTER(c_void_p)
        )
        enumerator_table = ctypes.cast(
            enumerator, POINTER(POINTER(c_void_p))
        ).contents
        device = c_void_p()
        hr = get_default(enumerator_table[4])(enumerator, 1, 0, byref(device))
        if hr != 0:
            return False
        activate = WINFUNCTYPE(
            ctypes.c_long,
            c_void_p,
            POINTER(_GUID),
            c_uint,
            c_void_p,
            POINTER(c_void_p),
        )
        device_table = ctypes.cast(device, POINTER(POINTER(c_void_p))).contents
        endpoint = c_void_p()
        volume_id = _guid("5CDF2C82-841E-4546-9722-0CF74078229A")
        hr = activate(device_table[3])(device, byref(volume_id), 1, None, byref(endpoint))
        if hr != 0:
            return False
        endpoint_table = ctypes.cast(endpoint, POINTER(POINTER(c_void_p))).contents
        muted = c_uint()
        get_mute = WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_uint))
        hr = get_mute(endpoint_table[15])(endpoint, byref(muted))
        if hr != 0 or muted.value == 0:
            return False
        set_mute = WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, c_void_p)
        hr = set_mute(endpoint_table[14])(endpoint, 0, None)
        return hr == 0
    except Exception:
        return False


def _host_name(hostapis, device) -> str:
    index = device.get("hostapi", 0)
    if index < 0 or index >= len(hostapis):
        return ""
    return hostapis[index].get("name", "")


def choose_device(devices, hostapis, needle: str, want_input: bool):
    """Pick the MME device whose name contains needle. Other host APIs are a fallback."""
    needle = needle.lower()
    found = []
    for index, device in enumerate(devices):
        channels = (
            device.get("max_input_channels", 0)
            if want_input
            else device.get("max_output_channels", 0)
        )
        if channels < 1:
            continue
        if needle not in device.get("name", "").lower():
            continue
        prefer = 0 if _host_name(hostapis, device) == "MME" else 1
        found.append((prefer, index, device["name"]))
    if not found:
        return None
    found.sort()
    return found[0][1], found[0][2]


def microphone_inputs(devices, hostapis) -> list[tuple[int, str]]:
    """Built-in and headset microphones. Skips loopback and mapper devices."""
    chosen = []
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) < 1:
            continue
        if _host_name(hostapis, device) != "MME":
            continue
        name = device.get("name", "")
        lowered = name.lower()
        if "microphone" not in lowered:
            continue
        if "mapper" in lowered:
            continue
        chosen.append((index, name))
    return chosen


def resolve_input(sd):
    devices = list(sd.query_devices())
    hostapis = list(sd.query_hostapis())
    mics = microphone_inputs(devices, hostapis)
    if mics:
        return mics
    chosen = choose_device(devices, hostapis, "microphone", True)
    if chosen is not None:
        return [chosen]
    default_index = sd.default.device[0]
    info = sd.query_devices(default_index)
    return [(default_index, info["name"])]


def is_headset_name(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in ("headphone", "headset", "earphone"))


def playback_kind(active_names: list[str]) -> str:
    """Headphones when a headset is connected. Laptop speakers otherwise."""
    for name in active_names:
        if is_headset_name(name):
            return "headphones"
    return "speakers"


def active_render_names() -> list[str]:
    """Names of playback devices that are plugged in or connected."""
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    enumerator = c_void_p()
    hr = ole32.CoCreateInstance(
        byref(_guid("BCDE0395-E52F-467C-8E3D-C4579291692E")),
        None,
        1,
        byref(_guid("A95664D2-9614-4F35-A746-DE8DB63617E6")),
        byref(enumerator),
    )
    if hr != 0:
        return []
    enumerator_table = ctypes.cast(enumerator, POINTER(POINTER(c_void_p))).contents
    enum_endpoints = WINFUNCTYPE(
        ctypes.c_long, c_void_p, c_uint, c_uint, POINTER(c_void_p)
    )
    collection = c_void_p()
    hr = enum_endpoints(enumerator_table[3])(enumerator, 0, 0xF, byref(collection))
    if hr != 0:
        return []
    collection_table = ctypes.cast(collection, POINTER(POINTER(c_void_p))).contents
    get_count = WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_uint))
    item = WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, POINTER(c_void_p))
    count = c_uint()
    get_count(collection_table[3])(collection, byref(count))

    class _PropertyKey(Structure):
        _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]

    class _PropVariant(Structure):
        _fields_ = [
            ("vt", c_ushort),
            ("r1", c_ushort),
            ("r2", c_ushort),
            ("r3", c_ushort),
            ("val", c_void_p),
            ("pad", c_void_p),
        ]

    friendly = _PropertyKey(_guid("a45c254e-df1c-4efd-8020-67d146a850e0"), 14)
    get_state = WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_uint))
    open_store = WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, POINTER(c_void_p))
    get_value = WINFUNCTYPE(
        ctypes.c_long, c_void_p, POINTER(_PropertyKey), POINTER(_PropVariant)
    )
    names = []
    for index in range(count.value):
        device = c_void_p()
        item(collection_table[4])(collection, index, byref(device))
        device_table = ctypes.cast(device, POINTER(POINTER(c_void_p))).contents
        state = c_uint()
        if get_state(device_table[6])(device, byref(state)) != 0 or state.value != 1:
            continue
        store = c_void_p()
        if open_store(device_table[4])(device, 0, byref(store)) != 0:
            continue
        store_table = ctypes.cast(store, POINTER(POINTER(c_void_p))).contents
        value = _PropVariant()
        if get_value(store_table[5])(store, byref(friendly), byref(value)) != 0:
            continue
        if value.vt == 31 and value.val:
            names.append(ctypes.wstring_at(value.val))
    return names


def resolve_output(sd):
    devices = list(sd.query_devices())
    hostapis = list(sd.query_hostapis())
    try:
        active = active_render_names()
    except Exception:
        active = []
    if not active:
        info = sd.query_devices(sd.default.device[1])
        active = [info["name"]]
    needle = "headphone" if playback_kind(active) == "headphones" else "speakers"
    chosen = choose_device(devices, hostapis, needle, False)
    if chosen is None and needle == "headphone":
        chosen = choose_device(devices, hostapis, "speakers", False)
    if chosen is not None:
        return chosen
    default_index = sd.default.device[1]
    info = sd.query_devices(default_index)
    return default_index, info["name"]
