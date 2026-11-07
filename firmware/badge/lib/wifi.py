"""Join WiFi using credentials in /data/wifi.json.

/data/wifi.json looks like:
    {"ssid": "MyNetwork", "password": "secret"}
or, to try several networks in order:
    [{"ssid": "Supercon", "password": "..."}, {"ssid": "Home", "password": "..."}]
"""

import json
import time

import network

# mDNS name: the badge answers as <HOSTNAME>.local (used by ./dev.sh ota).
HOSTNAME = "kevin-badge"

_wlan = network.WLAN(network.STA_IF)


class WifiError(Exception):
    pass


def _networks():
    try:
        with open("/data/wifi.json") as f:
            conf = json.load(f)
    except OSError:
        raise WifiError("No /data/wifi.json on the badge")
    except ValueError:
        raise WifiError("/data/wifi.json is not valid JSON")
    if isinstance(conf, dict):
        conf = [conf]
    return conf


def is_connected() -> bool:
    return _wlan.active() and _wlan.isconnected()


def off():
    """Radio off (battery mode). connect() turns it back on when needed."""
    if _wlan.active():
        try:
            _wlan.disconnect()
        except OSError:
            pass
        _wlan.active(False)
        print("wifi: off")


def connect(timeout_s: int = 20) -> str:
    """Connect if needed. Returns the IP address or raises WifiError."""
    if is_connected():
        return _wlan.ifconfig()[0]
    nets = _networks()
    try:
        network.hostname(HOSTNAME)  # must be set before the interface is up
    except Exception:
        pass
    _wlan.active(True)
    # SSID -> name as broadcast. Matching ignores case ("supercon" finds
    # "Supercon"), but the join uses the exact broadcast name.
    visible = {}
    for s in _wlan.scan():
        name = s[0].decode()
        visible[name.lower()] = name
    problems = []
    for net in nets:
        wanted = net.get("ssid", "")
        ssid = visible.get(wanted.lower())
        if ssid is None:
            problems.append("%s: not in range" % wanted)
            continue
        print("wifi: joining", ssid)
        _wlan.connect(ssid, net.get("password", ""))
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_s * 1000:
            if _wlan.isconnected():
                ip = _wlan.ifconfig()[0]
                print("wifi: connected", ip)
                return ip
            time.sleep_ms(200)
        problems.append("%s: join failed (status %d) - check the password" % (ssid, _wlan.status()))
        _wlan.disconnect()
    raise WifiError("; ".join(problems) or "no networks in /data/wifi.json")
