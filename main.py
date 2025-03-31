import argparse
import json
import os
import subprocess
import sys
import time
import re
from datetime import timedelta
import ctypes

from smartcard.Exceptions import NoCardException, CardConnectionException
from smartcard.System import readers
from smartcard.util import toHexString

APPS = {
    "mem": {
        "install": ["--run", "99848a60/install"],
        "uninstall": ["--run", "99848a60/destroy"],
    },
    "tesla": {
        "install": ["--run", "e819c674/install"],
        "uninstall": ["--run", "e819c674/destroy"],
    },
    "fido": {
        "install": ["--run", "cc68e88c/install"],
        "uninstall": ["--run", "cc68e88c/destroy"],
    },
    "nfc": {
        "install": [
            "--fields",
            "url='',size=256,readonly=false",
            "--run",
            "61b4b03d/cmac_custom",
        ],
        "uninstall": ["--run", "61b4b03d/destroy"],
    },
    "hmac": {
        "install": ["--run", "2f2e363b/install"],
        "uninstall": ["--run", "2f2e363b/destroy"],
    },
    "pgp": {
        "install": ["--run", "30c2ea30/install"],
        "uninstall": ["--run", "30c2ea30/destroy"],
    },
    "otp": {
        "install": ["--run", "61fc54d5/install"],
        "uninstall": ["--run", "61fc54d5/destroy"],
    },
}

FILENAME = f"applet_storage_by"


def is_jcop(reader):
    """Send SELECT APDUs"""
    SELECT = [0x00, 0xA4, 0x04, 0x00]
    try:
        connection = reader.createConnection()
        connection.connect()
        data, sw1, sw2 = connection.transmit(SELECT)
        connection.disconnect()
        return hex(sw1) == "0x90" and sw2 == 0

    except Exception as e:
        return False


def get_card_uid(reader):
    """Retrieve card UID with [FF CA 00 00 00]."""
    connection = None
    try:
        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        connection = reader.createConnection()
        connection.connect()
        response, sw1, sw2 = connection.transmit(GET_UID)

        if (sw1, sw2) == (0x90, 0x00):
            return toHexString(response)
    except (NoCardException, CardConnectionException):
        return None


def get_memory(reader, retry=0):
    """
    Returns a dict of the memory values
    :return:
    """
    try:
        connection = reader.createConnection()
        connection.connect()
        # Select the applet
        # info: Sending applet selection
        data, sw1, sw2 = connection.transmit(
            [
                0x00,
                0xA4,
                0x04,
                0x00,
                0x0C,
                0xA0,
                0x00,
                0x00,
                0x08,
                0x46,
                0x6D,
                0x65,
                0x6D,
                0x6F,
                0x72,
                0x79,
                0x01,
            ]
        )
    except (CardConnectionException, NoCardException) as e:
        if retry > 10:
            print(e)
            return None

        time.sleep(0.1)
        return get_memory(reader, retry=retry + 1)

    connection.disconnect()
    if sw1 == 0x90 and sw2 == 0x00:
        # success: Applet selected, card response is ok
        # Parse response
        memory_persistent = int.from_bytes(data[0:4], "big")
        memory_persistent_total = int.from_bytes(data[4:8], "big")
        memory_persistent_percentage = min(
            ## 99% at most because we'll at least have free memory installed
            0.99,
            memory_persistent / memory_persistent_total,
        )
        memory_transient_reset = int.from_bytes(data[8:10], "big")
        memory_transient_deselect = int.from_bytes(data[10:12], "big")
        memory_transient_free = min(
            1.0,
            (((memory_transient_reset + memory_transient_deselect) / 2.0) / 4096.0),
        )

        return {
            # Storage
            "persistent": {
                "free": memory_persistent,
                "total": memory_persistent_total,
                "used": memory_persistent_total - memory_persistent,
                "percent_free": memory_persistent_percentage,
            },
            # "RAM"
            "transient": {
                "reset_free": memory_transient_reset,
                "deselect_free": memory_transient_deselect,
                "percent_free": memory_transient_free,
            },
        }
    else:
        sw1 = f"{sw1:02x}"
        sw2 = f"{sw2:02x}"

        if sw1 == "6a" and sw2 == "82":
            # App not installed
            return -1


def get_installed_apps(reader):
    regex = r"([a-f0-9]{8}) -"
    app_regex = re.compile(regex)

    result = run_fdsm_command(reader, ["--card-apps"])

    if len(result.stderr) > 0:
        print(f"Error: {result.stderr}")

    regex_res = app_regex.search(result.stdout)

    return regex_res.groups()


def uninstall_by_recipe(reader, recipe: str):
    result = run_fdsm_command(reader, ["--run", f"{recipe}/destroy"])

    if len(result.stderr) > 0:
        print(f"Error: {result.stderr}")

    return result


def run_fdsm_command(reader, command: list[str], debug=False):
    command_list = ["java", "-jar", "fdsm.jar", "--reader", str(reader)]

    if debug:
        command_list.extend(["--verbose", "--trace-apdu", "--trace-api"])

    command_list.extend(command)

    result = subprocess.run(command_list, capture_output=True, text=True)

    if len(result.stderr) > 0:
        print(f"Error: {result.stderr}")

    return result


def run_as_admin():
    if ctypes.windll.shell32.IsUserAnAdmin():
        return  # Already running as admin
    else:
        # Get the current working directory
        cwd = os.getcwd()

        # Relaunch script with admin privileges, ensuring it starts in the same directory
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), cwd, 1
        )
        sys.exit()


if __name__ == "__main__":
    selected_apps = APPS.copy()
    del selected_apps["mem"]

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="This tool polls specific VK apps in the Fidesmo store to get storage requirements",
    )
    parser.add_argument(
        "--reader", type=str, help="Specify a reader by name. Defaults for first found."
    )
    parser.add_argument("--app", type=str, help="Check a specific app by name")

    args = parser.parse_args()

    if not args.h:
        run_as_admin()

    start_time = time.time()

    storage_by_app = {}

    readers = readers()

    if len(readers) == 0:
        print("Plugin a reader.")
        exit()

    if args.reader:
        try:
            r = next(x for x in readers if args.reader in x)
        except StopIteration:
            print(f"Error: unable to find {args.reader}. Defaulting to first found.")
            r = readers[0]
    else:
        r = readers[0]

    print(f"Reader: {r}")

    uid = get_card_uid(r)
    if not uid:
        print("No card present")
        exit()

    print(f"Card present: {uid}")

    if not is_jcop(r):
        print("That's not a smartcard.")
        exit()

    # Check for existing apps and remove them
    installed_apps = get_installed_apps(r)

    # Clear anything installed
    for app in installed_apps:
        if app != "99848a60":  # except free memory
            uninstall_by_recipe(r, app)

    if args.app:
        args.app = args.app.lower()
        if APPS.get(args.app):
            selected_apps = {args.app: APPS[args.app]}
        else:
            print(f"Error: app '{args.app}' is not found")
            exit()

    print()

    for each in list(selected_apps.keys()):
        app_name = each
        print(f"Checking {app_name}...".ljust(25), end="")

        pre_install = get_memory(r)

        if pre_install == -1:  # Free memory not installed... Let's install it
            run_fdsm_command(r, APPS["mem"]["install"])
            pre_install = get_memory(r)

        while pre_install is None:
            pre_install = get_memory(r)

        app_start_time = time.time()

        # Install
        res = run_fdsm_command(str(r), APPS[app_name]["install"])

        app_end_time = time.time()

        post_install = get_memory(r)

        while post_install is None:
            post_install = get_memory(r)

        # Remove
        run_fdsm_command(str(r), APPS[app_name]["uninstall"])

        storage_by_app[app_name] = {
            "persistent": post_install["persistent"]["used"]
            - pre_install["persistent"]["used"],
            "transient": (
                pre_install["transient"]["reset_free"]
                + pre_install["transient"]["deselect_free"]
            )
            - (
                post_install["transient"]["reset_free"]
                + post_install["transient"]["deselect_free"]
            ),
        }

        if app_name == "nfc":  # remove the 256 bytes for the container size
            storage_by_app["nfc"]["persistent"] -= 256

        print(f"Installed in {time.time() - app_start_time:.02f} seconds")

    print()

    print(f"Elapsed time: {str(timedelta(seconds=int(time.time() - start_time)))}")

    with open(f"{FILENAME}_app.json", "w") as f:
        json.dump(storage_by_app, f, indent=4)

    if os.path.exists(f"{FILENAME}_app.json"):
        print("Success: Wrote storage by app")
    else:
        print("Failure: Unable to write storage by app")
