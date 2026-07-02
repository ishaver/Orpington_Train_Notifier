# Southeastern Orpington → London Bridge delay notifier

Checks live departures every 10 minutes on weekday mornings (up to 10:00 UK
time) and sends a phone push notification via [ntfy.sh](https://ntfy.sh) if
a train is delayed or cancelled. Runs entirely on GitHub Actions — free,
no server needed.

Data comes from [Huxley2](https://huxley2.azurewebsites.net), a free public
proxy for National Rail's live departure boards (Darwin API).

## Setup (5 minutes)

1. **Create the repo**
   Create a new GitHub repository and push these files to it (or use
   "Upload files" in the GitHub web UI to drag the whole folder in).

2. **Pick a notification topic**
   ntfy.sh works by topic name — anyone who knows the topic name can see
   your notifications, so pick something hard to guess, e.g.
   `piyush-orpington-trains-x7f2`.

3. **Install the ntfy app**
   - iOS: [App Store](https://apps.apple.com/app/ntfy/id1625396347)
   - Android: [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   Open the app, tap "+", and subscribe to the topic name you picked.

4. **Add the topic as a repo secret**
   In your GitHub repo: Settings → Secrets and variables → Actions →
   New repository secret.
   - Name: `NTFY_TOPIC`
   - Value: the topic name you picked in step 2

5. **Enable Actions**
   Go to the "Actions" tab in your repo and enable workflows if prompted.
   The workflow runs automatically every 10 minutes, 06:00–10:00 UK time,
   Monday to Friday.

6. **Test it**
   Go to Actions → "Southeastern Orpington -> London Bridge notifier" →
   "Run workflow" to trigger it manually and check the logs. If it's
   outside the 06:00–10:00 window it'll just log that it's skipping —
   that's expected, it means the logic is working.

## How it decides to notify

- Pulls the next 10 departures from Orpington to London Bridge.
- A train counts as a "problem" if its estimated departure time (`etd`)
  isn't `"On time"` — i.e. it shows a revised time or `"Cancelled"`.
- To avoid spamming you every 10 minutes about the same delayed train, it
  remembers (via a small cached `state.json`) what it already notified you
  about, and only notifies again if the status changes further (e.g. a
  6-minute delay becomes a 20-minute delay, or a delay becomes a
  cancellation).
- The dedup memory resets each day.

## Tweaking it

Open `check_trains.py`:
- `CUTOFF_HOUR` / `START_HOUR` — change the notification window.
- `NUM_ROWS` — how many upcoming departures to check each run.
- Swap `FROM_CRS`/`TO_CRS` if you ever want a different route (station
  codes are at `https://huxley2.azurewebsites.net/crs?query=stationname`).

To change how often it checks, edit the `cron` line in
`.github/workflows/train-notify.yml`. GitHub Actions doesn't guarantee
exact timing on the free tier — a 10-minute schedule may run a few
minutes late during busy periods, but is reliable enough for this.
