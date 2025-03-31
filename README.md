# Get App Storage

This is used to record the storage (persistent and transient) that VivoKey's Apex
apps use.

> [!CAUTION]
> Cards only use Fidesmo devices--the key used will brick other devices.

> [!INFO]
> Only works on Windows atm.

> [!IMPORTANT]
> Storage sizes are approximate--JCOP was never meant to be used this way.



Help:
```commandline
python main.py -h
```
```commandline
usage: main.py [-h] [--reader READER] [--app APP]

This tool polls specific VK apps in the Fidesmo store to get storage requirements

options:
  -h, --help       show this help message and exit
  --reader READER  Specify a reader by name. Defaults for first found.
  --app APP        Check a specific app by name

```

Example File:
```json
{
    "tesla": {
        "persistent": 3996,
        "transient": 68
    },
    "fido": {
        "persistent": 41748,
        "transient": 2745
    },
    "nfc": {
        "persistent": 4012,
        "transient": 20
    },
    "hmac": {
        "persistent": 4288,
        "transient": 276
    },
    "pgp": {
        "persistent": 25936,
        "transient": 2586
    },
    "otp": {
        "persistent": 6404,
        "transient": 2252
    }
}
```
