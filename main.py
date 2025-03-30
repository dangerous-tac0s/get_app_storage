import argparse
import json
import os
import subprocess
import time
import zipfile
import re
from datetime import timedelta

import chardet
import requests
from smartcard.Exceptions import NoCardException, CardConnectionException
from smartcard.System import readers
from smartcard.util import toHexString

REPOS = [
    {"owner": "dangerousthings", "repo": "flexsecure-applets"},
    {"owner": "arekinath", "repo": "PivApplet"},
    {"owner": "darconeous", "repo": "gauss-key-card"},
]

FILENAME = f"applet_storage_by"
DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"


def fetch_github_releases(owner: str, repo: str) -> list:
    """
    Fetch all releases from GitHub for the 'DangerousThings/flexsecure-applets' repo.

    Returns:
        list: A list of dictionaries, each representing a release, including version, tag, and other details.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        releases = []
        for release in data:
            release_info = {
                "tag_name": release.get("tag_name"),
                "name": release.get("name"),
                "published_at": release.get("published_at"),
                "assets": release.get("assets", []),
            }
            releases.append(release_info)

        return releases

    except requests.exceptions.RequestException as e:
        print(f"Error fetching releases: {e}")
        return []


def fetch_github_release(
    owner: str, repo: str, version=None | str, verbose=False
) -> dict[str, str] or dict[str]:
    """
    Fetch a release from GitHub for the 'DangerousThings/flexsecure-applets' repo.
    Defaults to the latest release if no version is specified.

    Args:
        version (str, optional): The version or tag of the release to fetch. Defaults to None (latest release).

    Returns:
        dict[str, str]: A dictionary with the asset name as the key and download URL as the value.
    """
    if version:
        # If a specific version is requested, fetch that release by tag name
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{version}"
    else:
        # If no version is specified, fetch the latest release
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        assets = data.get("assets", [])

        results = {}
        for asset in assets:
            if (
                ".cap" == asset["name"][-4:]
            ):  # Some releases other files # TODO: Handle gpg validation
                name = asset["name"]
                dl_url = asset["browser_download_url"]
                # Ensure the asset name is in the FLEXSECURE_AID_MAP if needed
                # if name in FLEXSECURE_AID_MAP:
                results[name] = dl_url

        if verbose:
            return {"apps": results, "version": data["tag_name"]}

        return results

    except requests.exceptions.RequestException as e:
        print(f"Error fetching release: {e}")
        return {}


def detect_encoding(file_path):
    """
    Detect the file encoding using chardet.

    Args:
        file_path (str): Path to the file.

    Returns:
        str: Detected encoding.
    """
    with open(file_path, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result["encoding"]


def extract_manifest_from_cap(cap_file_path, output_dir=None):
    """
    Extract the MANIFEST.MF file from a CAP archive and return a dictionary with all parsed data.

    Args:
        cap_file_path (str): Path to the CAP archive (ZIP file).
        output_dir (str, optional): Directory where the MANIFEST.MF will be saved. Defaults to None.

    Returns:
        dict: A dictionary containing all keys and values parsed from the MANIFEST.MF file.
    """
    try:
        with zipfile.ZipFile(cap_file_path, "r") as zip_ref:
            # List files in the archive to find 'META-INF/MANIFEST.MF'
            file_list = zip_ref.namelist()

            manifest_file = "META-INF/MANIFEST.MF"
            if manifest_file not in file_list:
                print(f"Error: {manifest_file} not found in the CAP archive.")
                return None

            # Extract the MANIFEST.MF content
            with zip_ref.open(manifest_file) as mf_file:
                # Temporarily write to a file to detect encoding
                temp_path = "temp_manifest.MF"
                with open(temp_path, "wb") as temp_file:
                    temp_file.write(mf_file.read())

                # Detect encoding of the MANIFEST.MF file
                encoding = detect_encoding(temp_path)

                # Read the content using the detected encoding
                with open(temp_path, "r", encoding=encoding) as temp_file:
                    manifest_content = temp_file.read()

                if output_dir:
                    # Optionally save the manifest to a file
                    output_file_path = os.path.join(output_dir, "MANIFEST.MF")
                    with open(output_file_path, "w") as output_file:
                        output_file.write(manifest_content)
                    print(f"MANIFEST.MF extracted to {output_file_path}")

                # Debug: Print manifest content to inspect structure
                # print("Manifest Content:\n", manifest_content)

                # Parse the manifest and extract all relevant fields
                return parse_manifest(manifest_content)

    except zipfile.BadZipFile:
        print(f"Error: The file {cap_file_path} is not a valid ZIP archive.")
        return None
    except Exception as e:
        print(cap_file_path)
        print(f"An error occurred while extracting the MANIFEST.MF: {e}")
        print(manifest_content)
        print()
        return None
    finally:
        try:
            os.remove(temp_path)
        except:
            pass


def parse_manifest(manifest_content: str) -> dict:
    """
    Parse the manifest content to extract all fields.

    Args:
        manifest_content (str): The contents of the extracted MANIFEST.MF file.

    Returns:
        dict: A dictionary containing all keys and values parsed from the manifest.
    """
    data = {}

    # Use a regular expression to find all key-value pairs in the manifest
    pattern = r"(?P<key>^[A-Za-z0-9\-]+):\s*(?P<value>.*)"
    matches = re.finditer(pattern, manifest_content, re.MULTILINE)

    for match in matches:
        key = match.group("key").strip()
        value = match.group("value").strip()

        # Parse AID fields (e.g., Java-Card-Applet-1-AID)
        if key == "Java-Card-Applet-AID":
            value = value.replace(":", "")

        # Fallback. VivoKey's OTP app has a mal-formed AID in 'Java-Card-Applet-AID'
        if key == "Classic-Package-AID":
            value = value.replace("aid", "").replace("/", "")

        # Parse version fields (e.g., Runtime-Descriptor-Version)
        elif key == "Java-Card-Package-Version" or key == "Runtime-Descriptor-Version":
            # Convert version to a tuple of integers
            value = value

            if key == "Runtime-Descriptor-Version" and len(value) < 3:
                while len(value) < 3:
                    value = tuple([*value, 0])

        data[key] = value

    return data


def get_selected_manifest(manifest_dict):
    return {
        "name": manifest_dict.get("Name", None),
        "aid": manifest_dict.get("Java-Card-Applet-AID", None)
        or manifest_dict.get("Classic-Package-AID", None),
        "app_version": manifest_dict.get("Java-Card-Package-Version", None),
        "jcop_version": manifest_dict.get("Runtime-Descriptor-Version", None),
    }


def is_jcop(reader):
    """Send SELECT APDUs"""
    SELECT = [0x00, 0xA4, 0x04, 0x00, 0x00]
    try:
        connection = reader.createConnection()
        connection.connect()
        data, sw1, sw2 = connection.transmit(SELECT)
        return hex(sw1) == "0x90" and sw2 == 0
    except Exception as e:
        return False


def get_card_uid(reader):
    """Retrieve card UID with [FF CA 00 00 00]."""
    try:
        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        connection = reader.createConnection()
        connection.connect()
        response, sw1, sw2 = connection.transmit(GET_UID)
        if (sw1, sw2) == (0x90, 0x00):
            return toHexString(response)
        return None
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

    # except NoCardException as e:
    #     if retry > 3:
    #         print(e)
    #         return None
    #
    #     return get_memory(reader, retry=retry + 1)

    if sw1 == 0x90 and sw2 == 0x00:
        # success: Applet selected, card response is ok
        # Parse response
        memory_persistent = int.from_bytes(data[0:4], "big")
        memory_persistent_total = int.from_bytes(data[5:7], "big")
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

        connection.disconnect()

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
        print("error: Card response: " + f"{sw1}" + " " + f"{sw2}")

        if sw1 == "6a" and sw2 == "82":
            # App not installed
            return -1

    connection.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="This tool polls select (or a specified) github repo for .cap files to determine their storage requirements.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        help=(
            "'app': Group versions within each app (default)\n"
            "'release': Group apps within releases\n"
            "'both|all': Generate both files"
        ),
    )

    parser.add_argument(
        "--owner", type=str, help="Github username. --repo param must be used as well"
    )
    parser.add_argument(
        "--repo", type=str, help="Github repo name. --owner param must be used as well"
    )

    args = parser.parse_args()

    MODE = args.mode or "app"
    if MODE.lower() == "both":
        MODE = "all"
    if MODE.lower() not in ["app", "release", "all"]:
        MODE = "app"

    if args.owner and args.repo:
        REPOS = [{"owner": args.owner, "repo": args.repo}]
    elif args.owner and not args.repo or not args.owner and args.repo:
        print("Both 'owner' and 'repo' are required if one is used")
        exit()

    start_time = time.time()

    storage_by_app_version = {}
    storage_by_release = {}

    latest_release = None

    readers = readers()

    if len(readers) == 0:
        print("Plugin a reader.")
        exit()

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

    print(f"Mode: {MODE}")
    print()

    for each in REPOS:
        owner = each["owner"]
        repo = each["repo"]
        releases = fetch_github_releases(owner=owner, repo=repo)

        if len(releases) > 0:
            print(f"{owner}/{repo}")
            print()

        for release in releases:
            if not latest_release:
                latest_release = release["tag_name"]

            print(f"Release: {release["tag_name"]}")
            response = fetch_github_release(
                owner=owner, repo=repo, version=release["tag_name"], verbose=True
            )

            apps = response["apps"]

            storage = {}

            for app_name, app_url in sorted(
                apps.items(), key=lambda item: item[0], reverse=True
            ):
                if app_name in ["javacard-memory.cap", "keycard.cap"]:
                    continue

                download_path = app_name

                # Download the file
                print(f"\tChecking {app_name}...".ljust(55), end=" ")

                try:
                    download_resp = requests.get(app_url, stream=True)
                    download_resp.raise_for_status()
                except ConnectionError as e:
                    print(e)
                    exit()

                with open(download_path, "wb") as f:
                    for chunk in download_resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Extract and parse the manifest
                parsed_manifest = extract_manifest_from_cap(download_path)
                if parsed_manifest:
                    select_parsed_manifest = get_selected_manifest(parsed_manifest)

                    if select_parsed_manifest.get("app_version"):
                        # Do we already have this version documented?
                        if (
                            MODE == "app"
                            and storage_by_app_version.get(app_name)
                            and storage_by_app_version[app_name].get(
                                select_parsed_manifest["app_version"]
                            )
                        ):
                            print("No change. Skipping.")
                            os.remove(download_path)
                            continue

                    # pprint.pprint(select_parsed_manifest, indent=4)
                    if select_parsed_manifest["aid"] is not None:
                        subprocess.run(
                            [
                                "gp.exe",
                                "--key",
                                DEFAULT_KEY,
                                "--delete",
                                select_parsed_manifest["aid"],
                            ],
                            capture_output=True,
                        )
                else:
                    print("Unable to parse manifest", end=" ")

                pre_install = get_memory(r)
                while pre_install is None:

                    pre_install = get_memory(r)

                app_start_time = time.time()

                subprocess.run(
                    ["gp.exe", "--key", DEFAULT_KEY, "--install", download_path],
                    capture_output=True,
                )

                app_end_time = time.time()

                post_install = get_memory(r)
                while post_install is None:
                    post_install = get_memory(r)

                subprocess.run(
                    ["gp.exe", "--key", DEFAULT_KEY, "--uninstall", download_path],
                    capture_output=True,
                )

                storage[app_name] = {
                    "meta": select_parsed_manifest,
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
                os.remove(download_path)

                if storage[app_name]["meta"]["app_version"]:
                    print(
                        f"v{storage[app_name]["meta"]["app_version"]}".ljust(23),
                        end=" ",
                    )

                print(f"Installed in {app_end_time - app_start_time:.03} seconds")

            for app in storage:
                if MODE in ["app", "all"]:
                    if not storage_by_app_version.get(app):
                        storage_by_app_version[app] = {}
                    storage_by_app_version[app][storage[app]["meta"]["app_version"]] = {
                        "persistent": storage[app]["persistent"],
                        "transient": storage[app]["transient"],
                    }
                if MODE in ["release", "all"]:
                    if not storage_by_release.get(release["tag_name"]):
                        storage_by_release[release["tag_name"]] = {}
                    storage_by_release[release["tag_name"]][app] = {
                        "persistent": storage[app]["persistent"],
                        "transient": storage[app]["transient"],
                    }
            print()

    print(f"Elapsed time: {str(timedelta(seconds=int(time.time() - start_time)))}")

    if MODE in ["app", "all"]:
        with open(f"{FILENAME}_app.json", "w") as f:
            json.dump(storage_by_app_version, f, indent=4)

        if os.path.exists(f"{FILENAME}_app.json"):
            print("Success: Wrote storage by app")
        else:
            print("Failure: Unable to write storage by app")

    if MODE in ["release", "all"]:
        with open(f"{FILENAME}_release.json", "w") as f:
            json.dump(storage_by_release, f, indent=4)

        if os.path.exists(f"{FILENAME}_release.json"):
            print("Success: Wrote storage by release")
        else:
            print("Failure: Unable to write storage by release")
