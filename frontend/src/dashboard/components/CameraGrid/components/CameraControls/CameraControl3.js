import * as React from 'react';
import Card from '@mui/material/Card';
import Grid from '@mui/material/Grid2';
import Button from '@mui/material/Button';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Select from '@mui/material/Select';
import Typography from '@mui/material/Typography';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { useEffect } from 'react';
import Stack from '@mui/material/Stack';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Paper from '@mui/material/Paper';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';
import {
  getCameraDevices,
  getCameraFeature,
  getCameraStatus,
  getFeatureList,
  getLatestShutter,
  restartCamera,
  saveFeature,
  setCameraFeature,
} from '../../../../../services/camera.api';

export default function CameraControl3() {
  const [openDialog, setOpenDialog] = React.useState(false);
  const [devices, setDevices] = React.useState([]);
  const [deviceMapping, setDeviceMapping] = React.useState({}); // { device_index: camera_id }
  const [loadingDevices, setLoadingDevices] = React.useState(false);
  const [isCapturing, setIsCapturing] = React.useState(false); // 촬영 중인지 여부
  const [cameraIPs, setCameraIPs] = React.useState({}); // { cameraNumber: ip_address }

  const [cameraValues, setCameraValues] = React.useState({
    camera1: {
      fps: '',
      exposureTime: '',
      gain: '',
      width: '',
      height: '',
    },
    camera2: {
      fps: '',
      exposureTime: '',
      gain: '',
      width: '',
      height: '',
    },
    camera3: {
      fps: '',
      exposureTime: '',
      gain: '',
      width: '',
      height: '',
    },
    camera4: {
      fps: '',
      exposureTime: '',
      gain: '',
      width: '',
      height: '',
    }
  });

  const [selectValues, setSelectValues] = React.useState({
    camera1: {
      manufacturer: 1,
      acquisitionFps: 0,
      gainAuto: 0,
      pixelFormat: 8,
      fpsresult: ''
    },
    camera2: {
      manufacturer: 1,
      acquisitionFps: 0,
      gainAuto: 0,
      pixelFormat: 8,
      fpsresult: ''
    },
    camera3: {
      manufacturer: 1,
      acquisitionFps: 0,
      gainAuto: 0,
      pixelFormat: 8,
      fpsresult: ''
    },
    camera4: {
      manufacturer: 1,
      acquisitionFps: 0,
      gainAuto: 0,
      pixelFormat: 8,
      fpsresult: ''
    }
  });



  const handleSelectChange = (camera, field) => (event) => {
    setSelectValues(prev => ({
      ...prev,
      [camera]: {
        ...prev[camera],
        [field]: event.target.value
      }
    }));
  };

  const handleTextFieldChange = (camera, field) => (event) => {
    setCameraValues(prev => ({
      ...prev,
      [camera]: {
        ...prev[camera],
        [field]: event.target.value
      }
    }));
  };

  const cameradbget = async (cameraNumber) => {
    try {
      const features = await getFeatureList();
      
      // 특정 카메라의 데이터만 찾기
      const feature = features.find(f => f.CAMERA === parseInt(cameraNumber));
      
      if (feature) {
        setCameraValues(prev => ({
          ...prev,
          [`camera${cameraNumber}`]: {
            fps: feature.FPS?.toString() || '9.4',
            exposureTime: feature.EXPOSURE_TIME?.toString() || '60000',
            gain: feature.GAIN_dB?.toString() || '10',
            width: feature.WIDTH?.toString() || '4096',
            height: feature.HEIGHT?.toString() || '3000',
          }
        }));

        setSelectValues(prev => ({
          ...prev,
          [`camera${cameraNumber}`]: {
            ...prev[`camera${cameraNumber}`],
            acquisitionFps: feature.FPS_ENABLE || 0,
            gainAuto: feature.GAIN_AUTO || 0,
            pixelFormat: feature.PIXEL_FORMAT || 8
          }
        }));
      } else {
        console.warn(`Camera ${cameraNumber} data not found`);
      }

    } catch (error) {
      console.error('Error fetching camera features:', error);
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      // DB에서 카메라 feature 가져오기 (IP 포함)
      try {
        const features = (await getFeatureList()) || [];
        
        // IP 정보 저장
        const ipMap = {};
        features.forEach(feature => {
          if (feature.CAMERA && feature.IP) {
            ipMap[feature.CAMERA] = feature.IP;
          }
        });
        setCameraIPs(ipMap);
      } catch (error) {
        console.error('Error fetching camera IPs:', error);
      }
      
      // 준비된 카메라(has_camera)만 하드웨어 get_feature 호출 — 미연결 슬롯은 건너뛰어 404 방지
      const checkAndFetchFeatures = async () => {
        const maxRetries = 5;
        const retryDelay = 1000;

        for (let attempt = 0; attempt < maxRetries; attempt++) {
          try {
            const statusResponse = await getCameraStatus();
            const statusData = statusResponse?.status;
            const cameras = statusData?.cameras || [];

            const availableUiNumbers = cameras
              .filter((c) => c.has_camera)
              .map((c) => String(c.camera_id + 1));

            if (availableUiNumbers.length > 0) {
              for (const cameraNum of availableUiNumbers) {
                try {
                  await cameraget(cameraNum, false);
                  await new Promise((resolve) => setTimeout(resolve, 100));
                } catch (err) {
                  console.warn(`Camera ${cameraNum} feature fetch failed:`, err);
                }
              }
              return;
            }

            if (statusData?.is_initialized) {
              console.warn(
                'Camera system reports initialized but no connected cameras (has_camera). Skipping get_feature.'
              );
              return;
            }
          } catch (error) {
            console.warn(`Attempt ${attempt + 1} failed to check camera status:`, error);
          }

          if (attempt < maxRetries - 1) {
            await new Promise((resolve) => setTimeout(resolve, retryDelay));
          }
        }

        console.warn(
          'Camera status unavailable after retries; skipping get_feature for all slots (avoids 404 on unused cameras).'
        );
      };
      
      checkAndFetchFeatures();
    };
    fetchData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const cameradbsave = async (cameraNumber) => {
    try {
      // 현재 선택된 값들 가져오기
      const gainAuto = selectValues[`camera${cameraNumber}`].gainAuto;
      const fpsEnable = selectValues[`camera${cameraNumber}`].acquisitionFps;
      
      // 카메라 설정 데이터 구성 (백엔드 스키마에 맞춤)
      const cameraData = {
        CAMERA: parseInt(cameraNumber),
        WIDTH: parseInt(cameraValues[`camera${cameraNumber}`].width),
        HEIGHT: parseInt(cameraValues[`camera${cameraNumber}`].height),
        EXPOSURE_TIME: parseFloat(cameraValues[`camera${cameraNumber}`].exposureTime),
        GAIN_AUTO: gainAuto,
        GAIN_dB: gainAuto === 0 ? parseFloat(cameraValues[`camera${cameraNumber}`].gain) : null,
        FPS: fpsEnable === 0 ? null : parseFloat(cameraValues[`camera${cameraNumber}`].fps),
        FPS_ENABLE: fpsEnable,
        PIXEL_FORMAT: selectValues[`camera${cameraNumber}`].pixelFormat
      };

      // 서버에 설정 저장 요청
      const data = await saveFeature(cameraData);
      console.log('Camera settings saved:', data);
      alert(`Camera ${cameraNumber} settings saved successfully!`);

    } catch (error) {
      console.error('Error saving camera settings:', error);
      alert(`Error saving camera ${cameraNumber} settings!`);
    }
  };

  // 픽셀 포맷 매핑 객체 추가
  const pixelFormatMap = {
    17301505: 1,  // 'PixelType_Gvsp_Mono8' 17301505
    17825795: 2,  // 'PixelType_Gvsp_Mono10' 17825795
    17825797: 3,  // 'PixelType_Gvsp_Mono12' 17825797   
    35127316: 4,  // 'PixelType_Gvsp_RGB8_Packed' 35127316
    35127317: 5,  // 'PixelType_Gvsp_BGR8_Packed' 35127317
    34603058: 6,  // 'PixelType_Gvsp_YUV422_YUYV_Packed' 34603058
    34603039: 7,  // 'PixelType_Gvsp_YUV422_Packed' 34603039
    17301513: 8,  // 'PixelType_Gvsp_BayerRG8' 17301513
    17825805: 9,  // 'PixelType_Gvsp_BayerRG10' 17825805
    17563687: 10, // 'PixelType_Gvsp_BayerRG10_Packed' 17563687
    17825809: 11, // 'PixelType_Gvsp_BayerRG12' 17825809
    17563691: 12  // 'PixelType_Gvsp_BayerRG12_Packed' 17563691
  };

  // 픽셀 포맷 변환 함수
  const convertPixelFormat = (pixelFormat) => {
    return pixelFormatMap[pixelFormat] || 8; // 매핑되지 않은 경우 기본값 8 반환
  };

  // UI 카메라 번호(1-4)를 백엔드 카메라 ID(0-3)로 변환
  const getCameraId = (cameraNumber) => {
    return parseInt(cameraNumber) - 1;
  };

  // 컴포넌트 마운트 시 저장된 매핑 정보 불러오기
  useEffect(() => {
    const savedMapping = localStorage.getItem('cameraDeviceMapping');
    if (savedMapping) {
      setDeviceMapping(JSON.parse(savedMapping));
    }
  }, []);

  const cameraget = async (cameraNumber, showAlert = false) => {
    try {
      const cameraId = getCameraId(cameraNumber);
      const data = await getCameraFeature(cameraId);
      if (!data?.feature) {
        throw new Error(`Failed to get camera ${cameraNumber} features`);
      }
      
      const feature = data.feature;

      // 함수형 업데이트를 사용하여 최신 상태를 보장
      setSelectValues(prev => ({
        ...prev,
        [`camera${cameraNumber}`]: {
          ...prev[`camera${cameraNumber}`],
          acquisitionFps: parseInt(feature.AcquisitionFrameRateEnable) || 0,
          gainAuto: parseInt(feature.GainAuto) || 0,
          pixelFormat: convertPixelFormat(feature.PixelFormat),
          fpsresult: parseFloat(feature.ResultingFrameRate || 0).toFixed(2) || '0.00'
        }
      }));

      setCameraValues(prev => ({
        ...prev,
        [`camera${cameraNumber}`]: {
          ...prev[`camera${cameraNumber}`],
          fps: parseFloat(feature.AcquisitionFrameRate || 0).toFixed(2) || '0',
          gain: parseFloat(feature.Gain || 0).toFixed(2) || '0',
          exposureTime: parseFloat(feature.ExposureTime || 0) || 0,
          width: parseInt(feature.Width || 0) || 0,
          height: parseInt(feature.Height || 0) || 0
        }
      }));

      console.log(`Camera ${cameraNumber} settings loaded:`, feature);
    } catch (error) {
      console.error(`Error loading camera ${cameraNumber} settings:`, error);
      if (showAlert) {
        alert(`Error loading camera ${cameraNumber} settings: ${error?.data?.error || error.message}`);
      }
      throw error; // 에러를 다시 throw하여 호출자가 처리할 수 있도록
    }
  };

  // 디바이스 리스트 조회
  const fetchDevices = async () => {
    setLoadingDevices(true);
    try {
      // 디바이스 리스트 가져오기
      const deviceResponse = await getCameraDevices();
      if (deviceResponse.status === 'success') {
        const deviceList = deviceResponse.devices || [];
        setDevices(deviceList);
        
        // DB에서 카메라 feature 가져오기 (IP 포함)
        let cameraFeatures = [];
        try {
          cameraFeatures = (await getFeatureList()) || [];
        } catch (error) {
          console.warn('Failed to fetch camera features from DB:', error);
        }
        
        // IP 기반 매핑 생성
        const newMapping = {};
        const usedDeviceIndices = new Set(); // 이미 매핑된 디바이스 추적
        
        // 1. DB에 IP가 있는 카메라부터 매핑
        cameraFeatures.forEach((feature) => {
          const cameraNumber = feature.CAMERA; // 1-4
          const cameraId = cameraNumber - 1; // 0-3 (백엔드 ID)
          const ipAddress = feature.IP;
          
          if (ipAddress) {
            // 디바이스 리스트에서 해당 IP와 일치하는 디바이스 찾기
            const matchedDevice = deviceList.find(
              device => device.ip_address === ipAddress && !usedDeviceIndices.has(device.device_index)
            );
            
            if (matchedDevice) {
              newMapping[matchedDevice.device_index] = cameraId;
              usedDeviceIndices.add(matchedDevice.device_index);
            }
            // 매칭되는 디바이스가 없으면 빈값 (매핑 안 함)
          }
        });
        
        // 2. IP가 없는 카메라는 인덱스 순서대로 매핑
        let deviceIndex = 0;
        for (let cameraId = 0; cameraId < 4; cameraId++) {
          // 이미 매핑된 카메라는 스킵
          const isAlreadyMapped = Object.values(newMapping).includes(cameraId);
          if (!isAlreadyMapped && deviceIndex < deviceList.length) {
            // 아직 사용되지 않은 디바이스 찾기
            while (deviceIndex < deviceList.length && usedDeviceIndices.has(deviceList[deviceIndex].device_index)) {
              deviceIndex++;
            }
            if (deviceIndex < deviceList.length) {
              newMapping[deviceList[deviceIndex].device_index] = cameraId;
              usedDeviceIndices.add(deviceList[deviceIndex].device_index);
              deviceIndex++;
            }
          }
        }
        
        setDeviceMapping(newMapping);
      }
    } catch (error) {
      console.error('Error fetching devices:', error);
      alert('디바이스 리스트를 불러오는데 실패했습니다.');
    } finally {
      setLoadingDevices(false);
    }
  };

  // 카메라 촬영 상태 확인 (shutter DB의 STATUS 값 확인)
  const checkCameraStatus = async () => {
    try {
      const shutterData = await getLatestShutter();
      if (shutterData && Array.isArray(shutterData) && shutterData.length > 0) {
        const shutterStatus = shutterData[0].STATUS; // 'S': 시작, 'P': 일시정지, 'E': 종료
        // 'E'가 아니면 촬영 중 (시작 또는 일시정지 상태)
        const isCurrentlyCapturing = shutterStatus !== 'E';
        setIsCapturing(isCurrentlyCapturing);
        return isCurrentlyCapturing;
      }
      // 데이터가 없으면 촬영 중이 아닌 것으로 간주
      setIsCapturing(false);
      return false;
    } catch (error) {
      console.error('Error checking camera status:', error);
      // 에러 발생 시 안전하게 촬영 중이 아닌 것으로 간주
      setIsCapturing(false);
      return false;
    }
  };

  // 팝업 열기
  const handleOpenDialog = async () => {
    setOpenDialog(true);
    await checkCameraStatus(); // 촬영 상태 확인
    fetchDevices();
  };

  // 팝업 닫기
  const handleCloseDialog = () => {
    setOpenDialog(false);
  };

  // 카메라 번호 매핑 변경
  const handleMappingChange = (deviceIndex, cameraId) => {
    const newMapping = { ...deviceMapping };
    // 기존에 같은 camera_id를 사용하는 매핑 제거
    Object.keys(newMapping).forEach(key => {
      if (newMapping[key] === parseInt(cameraId)) {
        delete newMapping[key];
      }
    });
    // 새로운 매핑 추가
    if (cameraId !== '') {
      newMapping[deviceIndex] = parseInt(cameraId);
    } else {
      delete newMapping[deviceIndex];
    }
    setDeviceMapping(newMapping);
  };

  // 매핑 저장
  const handleSaveMapping = async () => {
    try {
      // 촬영 상태 재확인
      const isCurrentlyCapturing = await checkCameraStatus();
      
      if (isCurrentlyCapturing) {
        alert('촬영 중에는 카메라 매핑을 변경할 수 없습니다. 촬영을 종료한 후 다시 시도해주세요.');
        return;
      }
      
      // 로컬 스토리지에 매핑 저장
      localStorage.setItem('cameraDeviceMapping', JSON.stringify(deviceMapping));
      
      // 각 카메라 번호에 매핑된 디바이스의 IP를 DB에 저장
      const savePromises = [];
      
      // deviceMapping을 순회하면서 각 카메라 번호에 매핑된 디바이스 찾기
      Object.keys(deviceMapping).forEach(deviceIndexStr => {
        const deviceIndex = parseInt(deviceIndexStr);
        const cameraId = deviceMapping[deviceIndex]; // 0-3
        
        // 해당 디바이스 찾기
        const device = devices.find(d => d.device_index === deviceIndex);
        
        if (device && device.ip_address) {
          // UI 카메라 번호는 1-4이므로 cameraId + 1
          const cameraNumber = cameraId + 1;
          
          // DB에 IP 저장 (기존 레코드가 있으면 업데이트, 없으면 생성)
          const savePromise = saveFeature({
            CAMERA: cameraNumber, // DB에는 1-4로 저장
            IP: device.ip_address
          });
          
          savePromises.push(savePromise);
        }
      });
      
      // 모든 IP 저장 요청 실행
      if (savePromises.length > 0) {
        await Promise.all(savePromises);
        alert('카메라 매핑 및 IP 주소가 저장되었습니다.');
        
        // IP 정보 다시 가져오기
        try {
          const features = (await getFeatureList()) || [];
          const ipMap = {};
          features.forEach(feature => {
            if (feature.CAMERA && feature.IP) {
              ipMap[feature.CAMERA] = feature.IP;
            }
          });
          setCameraIPs(ipMap);
        } catch (error) {
          console.error('Error refreshing camera IPs:', error);
        }
        
        // 카메라 재초기화 (새로운 매핑 적용)
        try {
          const restartResponse = await restartCamera();
          if (restartResponse && restartResponse.message) {
            console.log('Camera restarted successfully with new mapping');
          } else {
            console.warn('Camera restart response:', restartResponse);
          }
        } catch (error) {
          console.error('Error restarting camera:', error);
          alert('카메라 매핑은 저장되었지만 재초기화에 실패했습니다. 카메라 서버를 재시작해주세요.');
        }
      } else {
        alert('카메라 매핑이 저장되었습니다. (매핑된 디바이스가 없습니다)');
      }
      
      handleCloseDialog();
    } catch (error) {
      console.error('Error saving camera mapping:', error);
      alert('카메라 매핑 저장 중 오류가 발생했습니다: ' + (error?.data?.detail || error.message));
    }
  };

  const camerasave = async (cameraNumber) => {
    try {
      // 현재 선택된 값들과 입력된 값들 가져오기
      const currentCamera = `camera${cameraNumber}`;
      const selectedValues = selectValues[currentCamera];
      const cameraInputs = cameraValues[currentCamera];

      // 카메라 설정 데이터 구성 - 백엔드 스키마에 맞춤
      const requestData = {
        feature: {
          fpsenable: parseInt(selectedValues.acquisitionFps) || 0,
          fps: parseFloat(cameraInputs.fps || '9.4') || 9.4,
          gainauto: parseInt(selectedValues.gainAuto) || 0,
          gain: parseFloat(cameraInputs.gain || '10') || 10,
          exposuretime: parseFloat(cameraInputs.exposureTime || '10000') || 10000,
          width: parseInt(cameraInputs.width || '4096') || 4096,
          height: parseInt(cameraInputs.height || '3000') || 3000,
          pixel_format: parseInt(selectedValues.pixelFormat) || 8
        }
      };

      console.log('Sending request data:', requestData);

      // 서버에 설정 저장 요청
      const cameraId = getCameraId(cameraNumber);
      const response = await setCameraFeature(cameraId, requestData);
      if (response) {
        console.log('Camera settings saved:', response);
        alert(`Camera ${cameraNumber} settings saved successfully!`);
        
        // 저장 후 현재 설정 다시 불러오기
        await cameraget(cameraNumber);
      }

    } catch (error) {
      console.error('Error saving camera settings:', error);
      if (error.data) {
        console.error('Response data:', error.data);
        console.error('Response status:', error.status);
      }
      alert(`Error saving camera ${cameraNumber} settings: ${error.message}`);
    }
  };
  

  return (    
    <Card sx={{ height: '100%' }}>     
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-start', mb: 2 }}>
        <Typography
          component="h1"
          variant="h5"
          sx={{ fontWeight: '600' }}
        >
          Camera Features 
        </Typography>
        <Button
          variant="outlined"
          color="primary"
          onClick={handleOpenDialog}
          sx={{ ml: 1 }}
          title="카메라 하드웨어 정보 조회 및 매핑"
        >
          Camera Mapping
        </Button>
      </Box>

      {/* 카메라 하드웨어 정보 조회 팝업 */}
      <Dialog 
        open={openDialog} 
        onClose={handleCloseDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pr: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography component="span" variant="h6">
                카메라 매핑 설정
              </Typography>
              <Button
                variant="outlined"
                onClick={fetchDevices}
                disabled={loadingDevices}
                size="small"
              >
                {loadingDevices ? '로딩 중...' : '리스트 새로고침'}
              </Button>
            </Box>
            <IconButton
              aria-label="닫기"
              onClick={handleCloseDialog}
              size="small"
            >
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          {isCapturing && (
            <Box 
              sx={{ 
                mb: 2, 
                p: 1.5, 
                bgcolor: 'warning.light', 
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'warning.main'
              }}
            >
              <Typography variant="body2" sx={{ color: 'warning.dark', fontWeight: 600 }}>
                ⚠️ 현재 촬영 중입니다. 촬영을 종료한 후에만 카메라 매핑을 변경할 수 있습니다.
              </Typography>
            </Box>
          )}
          
          {devices.length > 0 ? (
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>카메라 인덱스</TableCell>
                    <TableCell>모델명</TableCell>
                    <TableCell>IP 주소</TableCell>
                    <TableCell>MAC 주소</TableCell>
                    <TableCell>시리얼 번호</TableCell>
                    <TableCell>카메라 번호 매핑</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {devices.map((device) => (
                    <TableRow key={device.device_index}>
                      <TableCell>{device.device_index}</TableCell>
                      <TableCell>{device.model_name}</TableCell>
                      <TableCell>{device.ip_address}</TableCell>
                      <TableCell>{device.mac_address}</TableCell>
                      <TableCell>{device.serial_number}</TableCell>
                      <TableCell>
                        <Select
                          value={deviceMapping[device.device_index] !== undefined ? deviceMapping[device.device_index] : ''}
                          onChange={(e) => handleMappingChange(device.device_index, e.target.value)}
                          size="small"
                          sx={{ minWidth: 120 }}
                        >
                          <MenuItem value="">매핑 안함</MenuItem>
                          <MenuItem value={0}>카메라 1</MenuItem>
                          <MenuItem value={1}>카메라 2</MenuItem>
                          <MenuItem value={2}>카메라 3</MenuItem>
                          <MenuItem value={3}>카메라 4</MenuItem>
                        </Select>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Typography variant="body2" color="text.secondary">
              디바이스를 찾을 수 없습니다. 새로고침 버튼을 클릭하세요.
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>취소</Button>
          <Button 
            onClick={handleSaveMapping} 
            variant="contained" 
            color="primary"
            disabled={isCapturing}
            title={isCapturing ? '촬영 중에는 카메라 매핑을 변경할 수 없습니다.' : ''}
          >
            저장
          </Button>
        </DialogActions>
      </Dialog> 

      <Grid 
        container 
        spacing={1} 
        columns={12}
      >        
        <Grid size={{ xs: 2, lg: 3 }}>
          <Typography
            component="h2"
            variant="subtitle2"
            gutterBottom
            sx={{ fontWeight: '600' }}
          >
            Camera 1 {cameraIPs[1] && `(${cameraIPs[1]})`}
          </Typography>

          <List
            sx={{ width: '100%', maxWidth: 360, bgcolor: 'background.paper' }}
            component="nav"
            aria-labelledby="nested-list-subheader"
          >
            <ListItem
              secondaryAction={
                <Select
                  labelId="Acquisitionfps"
                  id="Acquisitionfps"
                  value={selectValues.camera1.acquisitionFps}
                  label="acquisitionFps"
                  onChange={handleSelectChange('camera1', 'acquisitionFps')}
                >
                  <MenuItem value={0}>Auto</MenuItem>
                  <MenuItem value={1}>Manual</MenuItem>
                </Select>
              }
            >
            <ListItemText primary="Acquisition FPS"/>
            </ListItem>
            
            <ListItem
              secondaryAction={
                <TextField
                  size="small"
                  value={cameraValues.camera1.fps}
                  onChange={handleTextFieldChange(`camera1`, 'fps')}
                  disabled={selectValues[`camera1`].acquisitionFps === 0}
                  sx={{ width: '100px' }}
                />
              }
            >
            <ListItemText primary="Setting FPS"/>
            </ListItem>

            <ListItem
              secondaryAction={
                <TextField
                  type="number"
                  value={selectValues.camera1.fpsresult}
                  disabled
                  sx={{ width: '100px' }}
                />
              }
            >
            <ListItemText primary="Result FPS"/>
            </ListItem>

            <ListItem
              secondaryAction={
                <TextField
                  size="small"
                  value={cameraValues.camera1.exposureTime}
                  onChange={handleTextFieldChange('camera1', 'exposureTime')}
                  sx={{ width: '100px' }}
                />
              }
            >
            <ListItemText primary="Exposure Times(us)"/>
            </ListItem>

            <ListItem
              secondaryAction={
                <Select
                  labelId="gainauto"
                  id="gainauto"
                  value={selectValues.camera1.gainAuto}
                  label="gainAuto"
                  onChange={handleSelectChange('camera1', 'gainAuto')}
                >
                  <MenuItem value={0}>Off</MenuItem>
                  <MenuItem value={1}>Once</MenuItem>
                  <MenuItem value={2}>Continuous</MenuItem>
                </Select>
              }
            >
            <ListItemText primary="Gain Auto"/>
            </ListItem>

            <ListItem
              secondaryAction={
                <TextField
                  size="small"
                  value={cameraValues[`camera1`].gain}
                  onChange={handleTextFieldChange(`camera1`, 'gain')}
                  disabled={selectValues[`camera1`].gainAuto !== 0}
                  sx={{ width: '100px' }}
                />
              }
            >
            <ListItemText primary="Gain(dB)"/>
            </ListItem>

            <ListItem
              secondaryAction={
                <TextField
                  size="small"
                  value={cameraValues.camera1.width}
                  onChange={handleTextFieldChange('camera1', 'width')}
                  sx={{ width: '100px' }}
                />
              }
            >
            <ListItemText primary="Width"/>
            </ListItem>

            <ListItem
              secondaryAction={
                <TextField
                  size="small"
                  value={cameraValues.camera1.height}
                  onChange={handleTextFieldChange('camera1', 'height')}
                  sx={{ width: '100px' }}
                />
              }
            >
            <ListItemText primary="Height"/>
            </ListItem>

            <ListItem
              secondaryAction={
                <Select
                  labelId="pixelformat"
                  id="pixelformat"
                  value={selectValues.camera1.pixelFormat}
                  label="pixelFormat"
                  onChange={handleSelectChange('camera1', 'pixelFormat')}
                >
                  <MenuItem value={1}>Mono8</MenuItem>
                  <MenuItem value={2}>Mono10</MenuItem>
                  <MenuItem value={3}>Mono12</MenuItem>
                  <MenuItem value={4}>RGB8</MenuItem>
                  <MenuItem value={5}>BGR8</MenuItem>
                  <MenuItem value={6}>YUV422(YUYV) Packed</MenuItem>
                  <MenuItem value={7}>YUV422 Packed</MenuItem>
                  <MenuItem value={8}>Bayer RG 8</MenuItem>
                  <MenuItem value={9}>Bayer RG 10</MenuItem>
                  <MenuItem value={10}>Bayer RG 10 Packed</MenuItem>
                  <MenuItem value={11}>Bayer RG 12</MenuItem>
                  <MenuItem value={12}>Bayer RG 12 Packed</MenuItem>
                </Select>                
              }
            >
            <ListItemText primary="Pixel Format"/>
            </ListItem>
            
            <Stack spacing={2} sx={{ mt: 2 }}>
              {/* 상단 행: 현재 세팅, 세팅 적용 */}
              <Grid container spacing={2}>
                <Grid size={{ xs: 6 }}>
                  <Button
                    variant="contained"
                    size="large"
                    color="warning"
                    fullWidth
                    onClick={() => cameraget('1')}        
                  >
                    현재 세팅
                  </Button>
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <Button
                    variant="contained"
                    size="large"
                    color="warning"
                    fullWidth
                    onClick={() => camerasave('1')}        
                  >
                    세팅 적용
                  </Button>
                </Grid>
              </Grid>

              {/* 하단 행: 세팅 불러오기, 세팅 저장 */}
              <Grid container spacing={2}>
                <Grid size={{ xs: 6 }}>
                  <Button
                    variant="contained"
                    size="large"
                    color="success"
                    fullWidth
                    onClick={() => cameradbget('1')}        
                  >
                    세팅 불러오기
                  </Button>
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <Button
                    variant="contained"
                    size="large"
                    color="success"
                    fullWidth
                    onClick={() => cameradbsave('1')}        
                  >
                    세팅 저장
                  </Button>
                </Grid>
              </Grid>
            </Stack>
          </List>        
        </Grid>


        <Grid size={{ xs: 2, lg: 3 }}>
            <Typography
              component="h2"
              variant="subtitle2"
              gutterBottom
              sx={{ fontWeight: '600' }}
            >
              Camera 2 {cameraIPs[2] && `(${cameraIPs[2]})`}
            </Typography>            

            <List
              sx={{ width: '100%', maxWidth: 360, bgcolor: 'background.paper' }}
              component="nav"
              aria-labelledby="nested-list-subheader"
            >
              <ListItem
                secondaryAction={
                  <Select
                    labelId="Acquisitionfps2"
                    id="Acquisitionfps2"
                    value={selectValues.camera2.acquisitionFps}
                    label="acquisitionFps"
                    onChange={handleSelectChange('camera2', 'acquisitionFps')}
                  >
                    <MenuItem value={0}>Auto</MenuItem>
                    <MenuItem value={1}>Manual</MenuItem>
                  </Select>
                }
              >
                <ListItemText primary="Acquisition FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera2.fps}
                    onChange={handleTextFieldChange(`camera2`, 'fps')}
                    disabled={selectValues[`camera2`].acquisitionFps === 0}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Setting FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    type="number"
                    value={selectValues.camera2.fpsresult}
                    disabled
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Result FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera2.exposureTime}
                    onChange={handleTextFieldChange('camera2', 'exposureTime')}
                    sx={{ width: '100px' }}
                  />
                }
              >           
              <ListItemText primary="Exposure Times(us)"/>
              </ListItem>

              <ListItem
              secondaryAction={
                <Select
                  labelId="gainauto"
                  id="gainauto"
                  value={selectValues.camera2.gainAuto}
                  label="gainAuto"
                  onChange={handleSelectChange('camera2', 'gainAuto')}
                >
                  <MenuItem value={0}>Off</MenuItem>
                  <MenuItem value={1}>Once</MenuItem>
                  <MenuItem value={2}>Continuous</MenuItem>
                </Select>
                }
              >
              <ListItemText primary="Gain Auto"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={selectValues[`camera2`].gainAuto === 1 ? cameraValues[`camera2`].gain : ''}
                    onChange={handleTextFieldChange(`camera2`, 'gain')}
                    disabled={selectValues[`camera2`].gainAuto !== 0}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Gain(dB)"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera2.width}
                    onChange={handleTextFieldChange('camera2', 'width')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Width"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera2.height}
                    onChange={handleTextFieldChange('camera2', 'height')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Height"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <Select
                    labelId="pixelformat"
                    id="pixelformat"
                    value={selectValues.camera2.pixelFormat}
                    label="pixelFormat"
                    onChange={handleSelectChange('camera2', 'pixelFormat')}
                  >
                    <MenuItem value={1}>Mono8</MenuItem>
                    <MenuItem value={2}>Mono10</MenuItem>
                    <MenuItem value={3}>Mono12</MenuItem>
                    <MenuItem value={4}>RGB8</MenuItem>
                    <MenuItem value={5}>BGR8</MenuItem>
                    <MenuItem value={6}>YUV422(YUYV) Packed</MenuItem>
                    <MenuItem value={7}>YUV422 Packed</MenuItem>
                    <MenuItem value={8}>Bayer RG 8</MenuItem>
                    <MenuItem value={9}>Bayer RG 10</MenuItem>
                    <MenuItem value={10}>Bayer RG 10 Packed</MenuItem>
                    <MenuItem value={11}>Bayer RG 12</MenuItem>
                    <MenuItem value={12}>Bayer RG 12 Packed</MenuItem>
                  </Select>                
                }
              >
              <ListItemText primary="Pixel Format"/>
              </ListItem>              
              
                             <Stack spacing={2} sx={{ mt: 2 }}>
                 {/* 상단 행: 현재 세팅, 세팅 적용 */}
                 <Grid container spacing={2}>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="warning"
                       fullWidth
                       onClick={() => cameraget('2')}
                     >
                       현재 세팅
                     </Button>
                   </Grid>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="warning"
                       fullWidth
                       onClick={() => camerasave('2')}
                     >
                       세팅 적용
                     </Button>
                   </Grid>
                 </Grid>

                 {/* 하단 행: 세팅 불러오기, 세팅 저장 */}
                 <Grid container spacing={2}>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="success"
                       fullWidth
                       onClick={() => cameradbget('2')}
                     >
                       세팅 불러오기
                     </Button>
                   </Grid>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="success"
                       fullWidth
                       onClick={() => cameradbsave('2')}
                     >
                       세팅 저장
                     </Button>
                   </Grid>
                 </Grid>
               </Stack>

            </List>
        </Grid>

        <Grid size={{ xs: 2, lg: 3 }}>
            <Typography
              component="h2"
              variant="subtitle2"
              gutterBottom
              sx={{ fontWeight: '600' }}
            >
              Camera 3 {cameraIPs[3] && `(${cameraIPs[3]})`}
            </Typography>

            <List
              sx={{ width: '100%', maxWidth: 360, bgcolor: 'background.paper' }}
              component="nav"
              aria-labelledby="nested-list-subheader"
            >
              <ListItem
                secondaryAction={
                  <Select
                    labelId="Acquisitionfps3"
                    id="Acquisitionfps3"
                    value={selectValues.camera3.acquisitionFps}
                    label="acquisitionFps"
                    onChange={handleSelectChange('camera3', 'acquisitionFps')}
                  >
                    <MenuItem value={0}>Auto</MenuItem>
                    <MenuItem value={1}>Manual</MenuItem>
                  </Select>
                }
              >
                <ListItemText primary="Acquisition FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera3.fps}
                    onChange={handleTextFieldChange(`camera3`, 'fps')}
                    disabled={selectValues[`camera3`].acquisitionFps === 0}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Setting FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    type="number"
                    value={selectValues.camera3.fpsresult}
                    disabled
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Result FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera3.exposureTime}
                    onChange={handleTextFieldChange('camera3', 'exposureTime')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Exposure Times(us)"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <Select
                    labelId="gainauto3"
                    id="gainauto3"
                    value={selectValues.camera3.gainAuto}
                    label="gainAuto"
                    onChange={handleSelectChange('camera3', 'gainAuto')}
                  >
                    <MenuItem value={0}>Off</MenuItem>
                    <MenuItem value={1}>Once</MenuItem>
                    <MenuItem value={2}>Continuous</MenuItem>
                  </Select>
                }
              >
                <ListItemText primary="Gain Auto"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={selectValues[`camera3`].gainAuto === 1 ? cameraValues[`camera3`].gain : ''}
                    onChange={handleTextFieldChange(`camera3`, 'gain')}
                    disabled={selectValues[`camera3`].gainAuto !== 0}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Gain(dB)"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera3.width}
                    onChange={handleTextFieldChange('camera3', 'width')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Width"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera3.height}
                    onChange={handleTextFieldChange('camera3', 'height')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Height"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <Select
                    labelId="pixelformat"
                    id="pixelformat"
                    value={selectValues.camera3.pixelFormat}
                    label="pixelFormat"
                    onChange={handleSelectChange('camera3', 'pixelFormat')}
                  >
                    <MenuItem value={1}>Mono8</MenuItem>
                    <MenuItem value={2}>Mono10</MenuItem>
                    <MenuItem value={3}>Mono12</MenuItem>
                    <MenuItem value={4}>RGB8</MenuItem>
                    <MenuItem value={5}>BGR8</MenuItem>
                    <MenuItem value={6}>YUV422(YUYV) Packed</MenuItem>
                    <MenuItem value={7}>YUV422 Packed</MenuItem>
                    <MenuItem value={8}>Bayer RG 8</MenuItem>
                    <MenuItem value={9}>Bayer RG 10</MenuItem>
                    <MenuItem value={10}>Bayer RG 10 Packed</MenuItem>
                    <MenuItem value={11}>Bayer RG 12</MenuItem>
                    <MenuItem value={12}>Bayer RG 12 Packed</MenuItem>
                  </Select>                
                }
              >
              <ListItemText primary="Pixel Format"/>
              </ListItem>              

                             <Stack spacing={2} sx={{ mt: 2 }}>
                 {/* 상단 행: 현재 세팅, 세팅 적용 */}
                 <Grid container spacing={2}>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="warning"
                       fullWidth
                       onClick={() => cameraget('3')}
                     >
                       현재 세팅
                     </Button>
                   </Grid>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="warning"
                       fullWidth
                       onClick={() => camerasave('3')}
                     >
                       세팅 적용
                     </Button>
                   </Grid>
                 </Grid>

                 {/* 하단 행: 세팅 불러오기, 세팅 저장 */}
                 <Grid container spacing={2}>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="success"
                       fullWidth
                       onClick={() => cameradbget('3')}
                     >
                       세팅 불러오기
                     </Button>
                   </Grid>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="success"
                       fullWidth
                       onClick={() => cameradbsave('3')}
                     >
                       세팅 저장
                     </Button>
                   </Grid>
                 </Grid>
               </Stack>
            </List>
        </Grid>
        <Grid size={{ xs: 2, lg: 3 }}>
            <Typography
              component="h2"
              variant="subtitle2"
              gutterBottom
              sx={{ fontWeight: '600' }}
            >
              Camera 4 {cameraIPs[4] && `(${cameraIPs[4]})`}
            </Typography>

            <List
              sx={{ width: '100%', maxWidth: 360, bgcolor: 'background.paper' }}
              component="nav"
              aria-labelledby="nested-list-subheader"
            >           
              <ListItem
                secondaryAction={
                  <Select
                    labelId="Acquisitionfps4"
                    id="Acquisitionfps4"
                    value={selectValues.camera4.acquisitionFps}
                    label="acquisitionFps"
                    onChange={handleSelectChange('camera4', 'acquisitionFps')}
                  >
                    <MenuItem value={0}>Auto</MenuItem>
                    <MenuItem value={1}>Manual</MenuItem>
                  </Select>
                }
              >
                <ListItemText primary="Acquisition FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera4.fps}
                    onChange={handleTextFieldChange(`camera4`, 'fps')}
                    disabled={selectValues[`camera4`].acquisitionFps === 0}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Setting FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    type="number"
                    value={selectValues.camera4.fpsresult}
                    disabled
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Result FPS"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera4.exposureTime}
                    onChange={handleTextFieldChange('camera4', 'exposureTime')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Exposure Times(us)"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <Select
                    labelId="gainauto4"
                    id="gainauto4"
                    value={selectValues.camera4.gainAuto}
                    label="gainAuto"
                    onChange={handleSelectChange('camera4', 'gainAuto')}
                  >
                    <MenuItem value={0}>Off</MenuItem>
                    <MenuItem value={1}>Once</MenuItem>
                    <MenuItem value={2}>Continuous</MenuItem>
                  </Select>
                }
              >
                <ListItemText primary="Gain Auto"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={selectValues[`camera4`].gainAuto === 1 ? cameraValues[`camera4`].gain : ''}
                    onChange={handleTextFieldChange(`camera4`, 'gain')}
                    disabled={selectValues[`camera4`].gainAuto !== 0}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Gain(dB)"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera4.width}
                    onChange={handleTextFieldChange('camera4', 'width')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Width"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <TextField
                    size="small"
                    value={cameraValues.camera4.height}
                    onChange={handleTextFieldChange('camera4', 'height')}
                    sx={{ width: '100px' }}
                  />
                }
              >
              <ListItemText primary="Height"/>
              </ListItem>

              <ListItem
                secondaryAction={
                  <Select
                    labelId="pixelformat"
                    id="pixelformat"
                    value={selectValues.camera4.pixelFormat}
                    label="pixelFormat"
                    onChange={handleSelectChange('camera4', 'pixelFormat')}
                  >
                    <MenuItem value={1}>Mono8</MenuItem>
                    <MenuItem value={2}>Mono10</MenuItem>
                    <MenuItem value={3}>Mono12</MenuItem>
                    <MenuItem value={4}>RGB8</MenuItem>
                    <MenuItem value={5}>BGR8</MenuItem>
                    <MenuItem value={6}>YUV422(YUYV) Packed</MenuItem>
                    <MenuItem value={7}>YUV422 Packed</MenuItem>
                    <MenuItem value={8}>Bayer RG 8</MenuItem>
                    <MenuItem value={9}>Bayer RG 10</MenuItem>
                    <MenuItem value={10}>Bayer RG 10 Packed</MenuItem>
                    <MenuItem value={11}>Bayer RG 12</MenuItem>
                    <MenuItem value={12}>Bayer RG 12 Packed</MenuItem>
                  </Select>                
                }
              >
              <ListItemText primary="Pixel Format"/>
              </ListItem>              

                             <Stack spacing={2} sx={{ mt: 2 }}>
                 {/* 상단 행: 현재 세팅, 세팅 적용 */}
                 <Grid container spacing={2}>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="warning"
                       fullWidth
                       onClick={() => cameraget('4')}
                     >
                       현재 세팅
                     </Button>
                   </Grid>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="warning"
                       fullWidth
                       onClick={() => camerasave('4')}
                     >
                       세팅 적용
                     </Button>
                   </Grid>
                 </Grid>

                 {/* 하단 행: 세팅 불러오기, 세팅 저장 */}
                 <Grid container spacing={2}>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="success"
                       fullWidth
                       onClick={() => cameradbget('4')}
                     >
                       세팅 불러오기
                     </Button>
                   </Grid>
                   <Grid size={{ xs: 6 }}>
                     <Button
                       variant="contained"
                       size="large"
                       color="success"
                       fullWidth
                       onClick={() => cameradbsave('4')}
                     >
                       세팅 저장
                     </Button>
                   </Grid>
                 </Grid>
               </Stack>
            </List>
        </Grid>
      </Grid>
    </Card>
  );
}
