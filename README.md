# Get App Storage

This is used to record the storage (persistent and transient) that JCOP
apps use. This was spun off of [GlobalPlatform Pro App Manager](). It pulls a list of
release and then goes through them, extracting the manifest from each cap file. This
exists mainly as a model for the fdsm version.

> [!CAUTION]
> Cards with non-default keys may be bricked

> [!IMPORTANT]
> Storage sizes are approximate--JCOP was never meant to be used this way.

Currently only working for windows--you'll have to switch 'gp.exe' for *['java', '-jar', 'gp.jar'] 
to run elsewhere--and have Java.

This repo contains output examples of a run in 'all' mode.

```commandline
python main.py -h
```
```commandline
usage: main.py [-h] [--mode MODE] [--owner OWNER] [--repo REPO]

This tool polls select (or a specified) github repo for .cap files to determine their storage requirements.

options:
  -h, --help     show this help message and exit
  --mode MODE    'app': Group versions within each app (default)
                 'release': Group apps within releases
                 'both|all': Generate both files
  --owner OWNER  Github username. --repo param must be used as well
  --repo REPO    Github repo name. --owner param must be used as well
```

Modes:
- **app**: each app will contain the versions of the app and the corresponding data
  - Everytime we try a new release, we check to see if the version is already 
  noted. If so, we don't bother to install it. <10 minutes (for flexsecure-applets only).
- **release**: every release will contain every app in it along with the data.
  - This will install every app in every release. Pretty time-consuming. >1 hour (for flexsecure-applets only)
- '**all**'|'**both**': You'll get both files. Takes no more time than doing a 'release' mode.

If you wish to poll a repo not listed and don't feel like adding it to the list, or just want to check one
repo you can supply --owner and --repo params to target just that repo.

I tend to tee the output:
```powershell
python -u main.py | Tee-Object -FilePath get_app_storage_log.txt
```
```powershell
Reader: D-Logic uFR Zero 0
Card present: 04 1A 2A 42 F2 18 90
Mode: all

Release: v0.19.1
	Checking vivokey-otp.cap...                       v1.2                    Installed in 5.21 seconds
	Checking openjavacard-ndef-tiny.cap...            v1.0                    Installed in 3.37 seconds
	Checking openjavacard-ndef-full.cap...            v1.0                    Installed in 3.77 seconds
	Checking YkHMACApplet.cap...                      v1.0                    Installed in 4.0 seconds
	Checking U2FApplet.cap...                         v1.1                    Installed in 5.13 seconds
	Checking SmartPGPApplet-large.cap...              v1.0                    Installed in 13.4 seconds
	Checking SmartPGPApplet-default.cap...            v1.0                    Installed in 13.3 seconds
	Checking SeedKeeper.cap...                        v0.1                    Installed in 10.5 seconds
	Checking Satodime.cap...                          v0.2                    Installed in 7.66 seconds
	Checking SatoChip.cap...                          v0.6                    Installed in 12.0 seconds
	Checking FIDO2.cap...                             v0.4                    Installed in 20.9 seconds

Release: v0.19.0
...
```

mode: app
```json
{
  "vivokey-otp.cap": {
    "1.2": {
      "persistent": 5416,
      "transient": 248
    },
    "1.1": {
      "persistent": 5280,
      "transient": 2344
    },
    "1.0": {
      "persistent": 5128,
      "transient": 2344
    }
  },
  "openjavacard-ndef-tiny.cap": {
    "1.0": {
      "persistent": 1460,
      "transient": 0
    },
    "0.0": {
      "persistent": 1364,
      "transient": 0
    }
  },
  "openjavacard-ndef-full.cap": {
    "1.0": {
      "persistent": 2684,
      "transient": 0
    },
    "0.0": {
      "persistent": 2588,
      "transient": 0
    }
  },
  ...
}
```

mode: release
```json
{
  "v0.19.1": {
    "vivokey-otp.cap": {
      "persistent": 5416,
      "transient": 2344
    },
    "openjavacard-ndef-tiny.cap": {
      "persistent": 1460,
      "transient": 0
    },
    "openjavacard-ndef-full.cap": {
      "persistent": 2684,
      "transient": 0
    },
    "YkHMACApplet.cap": {
      "persistent": 3300,
      "transient": 352
    },
    "U2FApplet.cap": {
      "persistent": 4484,
      "transient": 0
    },
    "SmartPGPApplet-large.cap": {
      "persistent": 24948,
      "transient": 2662
    },
    "SmartPGPApplet-default.cap": {
      "persistent": 24948,
      "transient": 2102
    },
    "SeedKeeper.cap": {
      "persistent": 20364,
      "transient": 1219
    },
    "Satodime.cap": {
      "persistent": 11704,
      "transient": 944
    },
    "SatoChip.cap": {
      "persistent": 19276,
      "transient": 1363
    },
    "FIDO2.cap": {
      "persistent": 38564,
      "transient": 1365
    }
  },
  ...
}
```