# Start Disaster Button - Implementation Plan

## Overview
Add a "Start Disaster" button that:
1. App starts at step -1 (no disaster data loaded)
2. Clicking "Start Disaster" begins a 10-second countdown
3. After countdown: plays an alert chime MP3
4. After chime: shows a push notification banner with the severe typhoon warning text
5. Then loads step 0 data and enables the normal play/step buttons

## Changes

### 1. Copy MP3 to frontend assets
- Copy `data/audley_fergine-warning-alarm-loop-1-279206.mp3` into `frontend/src/assets/alarm.mp3`
- This way metro bundler can resolve it via `require()`

### 2. DisasterDemoContext.tsx
- Add `disasterStarted: boolean` to context value
- Add `startDisaster: () => void` to context value
- Change initial `currentStepIndex` from `0` to `-1`
- Guard the `loadInitialWeatherStep` effect so it only runs when `disasterStarted` is true
- When `startDisaster` is called, set `disasterStarted = true`, which triggers the initial data load and sets step to 0

### 3. AppTabs.tsx
- Add `disasterStarted` and `startDisaster` from context
- Add `countdownSeconds` state (null when not counting)
- Add "Start Disaster" button that appears when `!disasterStarted`
- On click: start 10-second countdown timer
- When countdown hits 0: play the alarm MP3 using `new Audio()`, show the custom alert banner, call `startDisaster()`
- Hide play/step buttons until disaster is started
- Show the warning notification: "Severe typhoon warning. Extreme flooding warning. Please follow your evacuation instructions to get to safety as soon as possible, we are coordinating with your connections."
