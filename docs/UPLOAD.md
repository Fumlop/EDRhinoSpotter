# Bookmark upload to a team server

Off by default. Sends your bookmarks to a server your team runs, so the team
sees each other's deposits. RhinoSpotter does not run or provide a server.

## Turn it on

EDMC > File > Settings > RhinoSpotter, under the separator:

1. Tick **Upload bookmarks to a team server, checked every 5 min**. A notice
   lists what is sent.
2. **Server URL (https://)**: the address the server's admin gave you.
   `http://` is refused except to localhost / 127.0.0.1 / ::1.
3. **Access Key**: the key the admin gave you.
4. **Send my CMDR name with them**: off sends `commander` as `anonymous`.
5. OK. The panel shows an upload line while uploads are on.

## What the panel line says

| Line | Do |
|---|---|
| `N bookmarks uploaded` | nothing |
| `Upload refused - check the access key in Settings` | fix the key (server answered 401) |
| `Upload server unreachable - check the URL in Settings` | fix the URL, or the server is down |
| `Upload server URL must start with https:// - fix it in Settings` | fix the URL |
| `Upload server offline - ask whoever runs it` | server answered 502 |
| `Upload server error - ask whoever runs it` | any other answer; code in the EDMC log |

A connect error or timeout is tried 3 times, 5 s apart; any other failure
once. Either way the next check (5 min) tries again.

## What is sent

Every 5 min, the bookmarks that are new or changed since their last
successful upload, as `rs_api.bookmarks()` returns them ([API.md](API.md),
Bookmark keys): system, body, location, latitude, longitude, heading,
planet_radius, material, rigs, density, amount, depleted, depleted_at,
marked_at, updated_at, commander, id. The first check after turning it on
sends all of them.

"Changed" is a checksum over system, body, material, location, latitude,
longitude, rigs, density, amount, depleted, depleted_at, marked_at, kept in
`%LOCALAPPDATA%\RhinoSpotter\upload_data.json` (Linux:
`$XDG_DATA_HOME/RhinoSpotter`). Delete that file to send everything again.

## Server contract

One request per upload:

```
POST <Server URL>
Content-Type: application/json

{"access_key": "<Access Key>", "deposits": [<bookmark>, ...]}
```

| Answer | Plugin |
|---|---|
| 200 | marks the bookmarks sent; body ignored |
| 401 | "check the access key" |
| 502 | "server offline" |
| other | "server error"; code and first 200 chars of the body to the log |

Timeout 20 s. The same bookmark can arrive again after an edit; key it on
`system`, `body`, `latitude`, `longitude` or on `id` + `commander`.
