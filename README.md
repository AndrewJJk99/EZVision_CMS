# EZVision_CMS

## Windows setup

Requires Python 3.12 and Node.js/npm. Run from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm.cmd ci
```

The camera API also requires the camera vendor's SDK with `MvCameraControl.dll` available to Windows.

## Run

Run each service in a separate terminal from the project root:

| Service | Command | URL |
| --- | --- | --- |
| Camera API | `.\start-camera-api.bat` | http://localhost:17070 |
| CMS API | `.\start-cms-api.bat` | http://localhost:17060 |
| UI API | `.\start-ui-api.bat` | http://localhost:18000 |
| React frontend | `.\start-frontend.bat` | http://localhost:13000 |

To serve the production frontend, first run `npm.cmd run build` in `frontend`, then run `.\frontend\run_build.bat` from the project root instead of the React development server.

## Calibration session saving

A started session can be saved at any time, including before fitting or after a failed fit.
Captures, pending OFF corners, board settings, and available calibration results are preserved.
Computed models are saved in `backend/cms/laserplane_data` with quality diagnostics;
degenerate or weak calibration results show a warning and can still be saved.
Sessions without a computed model are saved in `backend/cms/session_data` and do not appear in the measurement model list.
