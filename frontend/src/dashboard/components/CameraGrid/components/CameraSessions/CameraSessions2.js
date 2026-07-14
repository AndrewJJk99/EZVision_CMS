import * as React from 'react';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Box from '@mui/material/Box';
import { getCameraStatus, getCameraWsUrl } from '../../../../../services/camera.api';
import { useCalibrationForCamera } from '../../context/CalibrationContext';
import { useCalibrationPreview } from '../../hooks/useCalibrationPreview';

export default function CameraSessions2({
  activeCameraCount = 1,
  enableResizeObserver = true,
  imageScale = 1,
  showControls = true,
}) {
  const canvasRef = React.useRef(null);
  const containerRef = React.useRef(null);
  const wsRef = React.useRef(null);
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [displayWidth, setDisplayWidth] = React.useState(1000);
  const displayWidthRef = React.useRef(1000);
  const activeCameraCountRef = React.useRef(activeCameraCount);
  const parentHeightRef = React.useRef(null);
  const cameraId = 2;
  const cameraIdBackend = cameraId - 1;
  const { isActive: calibrationActive } = useCalibrationForCamera(cameraIdBackend);
  const calibrationActiveRef = React.useRef(calibrationActive);
  const autoStartCheckedRef = React.useRef(false);
  const manualToggleRef = React.useRef(false);

  React.useEffect(() => {
    calibrationActiveRef.current = calibrationActive;
  }, [calibrationActive]);

  React.useEffect(() => {
    if (!calibrationActive) return;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
      setIsStreaming(false);
    }
  }, [calibrationActive]);

  useCalibrationPreview({
    enabled: calibrationActive,
    cameraIdBackend,
    canvasRef,
    containerRef,
    activeCameraCountRef,
    parentHeightRef,
  });

  React.useEffect(() => {
    activeCameraCountRef.current = activeCameraCount;
  }, [activeCameraCount]);

  // ResizeObserver: 부모 컨테이너 크기 변경 감지
  React.useEffect(() => {
    if (!enableResizeObserver) return () => {};
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { height } = entry.contentRect;
        if (parentHeightRef.current !== height) {
          parentHeightRef.current = height;
          // Canvas 크기 재계산
          const canvas = canvasRef.current;
          if (canvas && canvas.width > 0 && canvas.height > 0) {
            const aspectRatio = canvas.height / canvas.width;
            const windowWidth = window.innerWidth;
            const currentCameraCount = activeCameraCountRef.current || 1;
            let widthRatio = 1.0;
            let maxWidth = windowWidth;
            
            const availableWidth = windowWidth * widthRatio;
            const calculatedWidth = Math.floor(availableWidth / currentCameraCount);
            const minWidth = 300;
            let currentDisplayWidth = Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
            let calculatedHeight = currentDisplayWidth * aspectRatio;
            
            // 부모 컨테이너 높이 고려
            if (calculatedHeight > height) {
              currentDisplayWidth = Math.floor(height / aspectRatio);
              calculatedHeight = currentDisplayWidth * aspectRatio;
            }
            
            const ctx = canvas.getContext('2d');
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            
            canvas.width = currentDisplayWidth;
            canvas.height = calculatedHeight;
            
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = imageData.width;
            tempCanvas.height = imageData.height;
            const tempCtx = tempCanvas.getContext('2d');
            tempCtx.putImageData(imageData, 0, 0);
            
            ctx.drawImage(tempCanvas, 0, 0, currentDisplayWidth, calculatedHeight);
          }
        }
      }
    });

    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
    };
  }, [enableResizeObserver]);

  // 화면 크기에 따라 표시 너비 계산
  const calculateDisplayWidth = React.useCallback(() => {
    const windowWidth = window.innerWidth;
    const currentCameraCount = activeCameraCountRef.current || 1;
    
    let widthRatio = 1.0;
    let maxWidth = windowWidth;
    
    if (currentCameraCount === 1) {
      widthRatio = 0.75;
      maxWidth = 1200;
    } else if (currentCameraCount === 4) {
      widthRatio = 0.95;
      maxWidth = 1400;
    } else if (currentCameraCount === 3) {
      widthRatio = 0.92;
      maxWidth = 1200;
    }
    
    const availableWidth = windowWidth * widthRatio;
    const calculatedWidth = Math.floor(availableWidth / currentCameraCount);
    const minWidth = 300;
    return Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
  }, []);

  // activeCameraCount 변경 시 Canvas 크기 업데이트
  React.useEffect(() => {
    const updateCanvasSize = () => {
      const newWidth = calculateDisplayWidth();
      setDisplayWidth(newWidth);
      displayWidthRef.current = newWidth;
      
      // Canvas 크기를 즉시 업데이트
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        
        if (canvas.width > 0 && canvas.height > 0) {
          const aspectRatio = canvas.height / canvas.width;
          const windowWidth = window.innerWidth;
          
          let widthRatio = 1.0;
          let maxWidth = windowWidth;
          
          if (activeCameraCount === 1) {
            widthRatio = 0.75;
            maxWidth = 1200;
          } else if (activeCameraCount === 4) {
            widthRatio = 0.95;
            maxWidth = 1400;
          } else if (activeCameraCount === 3) {
            widthRatio = 0.92;
            maxWidth = 1200;
          }
          
          const availableWidth = windowWidth * widthRatio;
          const calculatedWidth = Math.floor(availableWidth / activeCameraCount);
          const minWidth = 300;
          let finalWidth = Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
          let finalHeight = finalWidth * aspectRatio;
          
          const parentBox = containerRef.current || canvas.parentElement;
          if (parentBox) {
            const parentHeight = parentBox.clientHeight || parentHeightRef.current;
            
            if (parentHeight) {
              const heightBasedWidth = Math.floor(parentHeight / aspectRatio);
              if (heightBasedWidth < finalWidth) {
                finalWidth = heightBasedWidth;
                finalHeight = finalWidth * aspectRatio;
              } else if (finalHeight > parentHeight) {
                finalWidth = Math.floor(parentHeight / aspectRatio);
                finalHeight = finalWidth * aspectRatio;
              }
              parentHeightRef.current = parentHeight;
            }
          }
          
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          canvas.width = finalWidth;
          canvas.height = finalHeight;
          
          const tempCanvas = document.createElement('canvas');
          tempCanvas.width = imageData.width;
          tempCanvas.height = imageData.height;
          const tempCtx = tempCanvas.getContext('2d');
          tempCtx.putImageData(imageData, 0, 0);
          ctx.drawImage(tempCanvas, 0, 0, finalWidth, finalHeight);
        } else {
          const windowWidth = window.innerWidth;
          
          let widthRatio = 1.0;
          let maxWidth = windowWidth;
          
          if (activeCameraCount === 1) {
            widthRatio = 0.75;
            maxWidth = 1200;
          } else if (activeCameraCount === 4) {
            widthRatio = 0.95;
            maxWidth = 1400;
          } else if (activeCameraCount === 3) {
            widthRatio = 0.92;
            maxWidth = 1200;
          }
          
          const availableWidth = windowWidth * widthRatio;
          const calculatedWidth = Math.floor(availableWidth / activeCameraCount);
          const minWidth = 300;
          let finalWidth = Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
          const aspectRatio = 0.75;
          let finalHeight = finalWidth * aspectRatio;
          
          const parentBox = containerRef.current || canvas.parentElement;
          if (parentBox) {
            const parentHeight = parentBox.clientHeight || parentHeightRef.current;
            
            if (parentHeight) {
              const heightBasedWidth = Math.floor(parentHeight / aspectRatio);
              if (heightBasedWidth < finalWidth) {
                finalWidth = heightBasedWidth;
                finalHeight = finalWidth * aspectRatio;
              } else if (finalHeight > parentHeight) {
                finalWidth = Math.floor(parentHeight / aspectRatio);
                finalHeight = finalWidth * aspectRatio;
              }
              parentHeightRef.current = parentHeight;
            }
          }
          
          canvas.width = finalWidth;
          canvas.height = finalHeight;
        }
      }
    };

    updateCanvasSize();
  }, [activeCameraCount, calculateDisplayWidth]);

  // 화면 크기 변경 감지
  React.useEffect(() => {
    const handleResize = () => {
      const newWidth = calculateDisplayWidth();
      setDisplayWidth(newWidth);
      displayWidthRef.current = newWidth;
    };

    const initialWidth = calculateDisplayWidth();
    setDisplayWidth(initialWidth);
    displayWidthRef.current = initialWidth;

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [calculateDisplayWidth]);

  // WebSocket 핸들러 설정
  const setupWebSocketHandlers = React.useCallback((websocket) => {
    websocket.onmessage = (messageEvent) => {
      if (calibrationActiveRef.current) return;

      const canvas = canvasRef.current;
      if (!canvas) {
        console.warn('[CameraSessions2] Canvas ref is null');
        return;
      }

      let blob;
      if (messageEvent.data instanceof Blob) {
        blob = messageEvent.data;
      } else if (messageEvent.data instanceof ArrayBuffer) {
        blob = new Blob([messageEvent.data], { type: 'image/jpeg' });
      } else {
        console.warn('[CameraSessions2] Unknown data type received:', typeof messageEvent.data);
        return;
      }
      
      const imageUrl = URL.createObjectURL(blob);
      const img = new Image();
      
      img.onload = () => {
        const ctx = canvas.getContext('2d');
        const aspectRatio = img.height / img.width;
        const windowWidth = window.innerWidth;
        const currentCameraCount = activeCameraCountRef.current || 1;
        
        let widthRatio = 1.0;
        let maxWidth = windowWidth;
        
        if (currentCameraCount === 1) {
          widthRatio = 0.75;
          maxWidth = 1200;
        } else if (currentCameraCount === 4) {
          widthRatio = 0.95;
          maxWidth = 1400;
        } else if (currentCameraCount === 3) {
          widthRatio = 0.92;
          maxWidth = 1200;
        }
        
        const availableWidth = windowWidth * widthRatio;
        const calculatedWidth = Math.floor(availableWidth / currentCameraCount);
        const minWidth = 300;
        let currentDisplayWidth = Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
        let calculatedHeight = currentDisplayWidth * aspectRatio;
        
        const parentBox = containerRef.current || canvas.parentElement;
        if (parentBox) {
          const parentHeight = parentBox.clientHeight || parentHeightRef.current;
          
          if (parentHeight) {
            const heightBasedWidth = Math.floor(parentHeight / aspectRatio);
            if (heightBasedWidth < currentDisplayWidth) {
              currentDisplayWidth = heightBasedWidth;
              calculatedHeight = currentDisplayWidth * aspectRatio;
            } else {
              calculatedHeight = currentDisplayWidth * aspectRatio;
              if (calculatedHeight > parentHeight) {
                currentDisplayWidth = Math.floor(parentHeight / aspectRatio);
                calculatedHeight = currentDisplayWidth * aspectRatio;
              }
            }
            parentHeightRef.current = parentHeight;
          }
        }
        
        canvas.width = currentDisplayWidth;
        canvas.height = calculatedHeight;
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(imageUrl);
      };
      
      img.onerror = (error) => {
        console.error('[CameraSessions2] Error loading image:', error);
        URL.revokeObjectURL(imageUrl);
      };
      
      img.src = imageUrl;
    };
  }, []);

  // 수동 스트리밍 토글 핸들러
  const handleStreamingToggle = React.useCallback(async (event) => {
    const shouldStream = event.target.checked;
    manualToggleRef.current = true;
    
    if (shouldStream) {
      try {
        const statusResponse = await getCameraStatus(cameraIdBackend);
        const status = statusResponse?.status;
        
        if (!status || !status.is_running) {
          alert(`카메라 ${cameraId}가 그래빙 중이 아닙니다. 먼저 "Start Grabbing" 버튼을 클릭해주세요.`);
          return;
        }
        
        if (wsRef.current) {
          wsRef.current.close();
        }
        
        const newWs = new WebSocket(getCameraWsUrl(cameraIdBackend));
        
        newWs.onopen = () => {
          console.log(`[CameraSessions2] Manual WebSocket connected for camera ${cameraId}`);
          wsRef.current = newWs;
          setIsStreaming(true);
          autoStartCheckedRef.current = true;
          newWs.binaryType = 'blob';
          setupWebSocketHandlers(newWs);
        };
        
        newWs.onerror = (error) => {
          console.error(`[CameraSessions2] Manual WebSocket error for camera ${cameraId}:`, error);
          setIsStreaming(false);
          autoStartCheckedRef.current = false;
          manualToggleRef.current = false;
        };
        
        newWs.onclose = (event) => {
          console.log(`[CameraSessions2] Manual WebSocket closed for camera ${cameraId}, code: ${event.code}`);
          wsRef.current = null;
          setIsStreaming(false);
          autoStartCheckedRef.current = false;
          manualToggleRef.current = false;
        };
      } catch (error) {
        console.error(`[CameraSessions2] Error starting manual streaming:`, error);
        setIsStreaming(false);
        manualToggleRef.current = false;
      }
    } else {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsStreaming(false);
      autoStartCheckedRef.current = false;
    }
  }, [cameraId, cameraIdBackend, setupWebSocketHandlers]);

  // 카메라 상태 확인 및 자동 스트리밍 시작
  const checkAndStartStreaming = React.useCallback(async () => {
    if (manualToggleRef.current || autoStartCheckedRef.current || isStreaming || wsRef.current) {
      return;
    }

    try {
      console.log(`[CameraSessions2] Checking camera ${cameraId} status for auto-start`);
      const statusResponse = await getCameraStatus(cameraIdBackend);
      const status = statusResponse?.status;
      
      if (status && status.is_running) {
        console.log(`[CameraSessions2] Camera ${cameraId} is running, starting auto-streaming`);
        autoStartCheckedRef.current = true;
        
        const newWs = new WebSocket(getCameraWsUrl(cameraIdBackend));
        
        newWs.onopen = () => {
          console.log(`[CameraSessions2] Auto-WebSocket connected for camera ${cameraId}`);
          wsRef.current = newWs;
          setIsStreaming(true);
          newWs.binaryType = 'blob';
          setupWebSocketHandlers(newWs);
        };
        
        newWs.onerror = (error) => {
          console.error(`[CameraSessions2] Auto-WebSocket error for camera ${cameraId}:`, error);
          autoStartCheckedRef.current = false;
        };
        
        newWs.onclose = (event) => {
          console.log(`[CameraSessions2] Auto-WebSocket closed for camera ${cameraId}, code: ${event.code}`);
          wsRef.current = null;
          setIsStreaming(false);
          autoStartCheckedRef.current = false;
        };
      } else {
        console.log(`[CameraSessions2] Camera ${cameraId} is not running, skipping auto-start`);
      }
    } catch (error) {
      console.error(`[CameraSessions2] Error checking camera status:`, error);
    }
  }, [cameraId, cameraIdBackend, isStreaming, setupWebSocketHandlers]);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      checkAndStartStreaming();
    }, 1000);

    const intervalId = setInterval(() => {
      if (!isStreaming && !wsRef.current) {
        autoStartCheckedRef.current = false;
        checkAndStartStreaming();
      }
    }, 5000);

    return () => {
      clearTimeout(timer);
      clearInterval(intervalId);
    };
  }, [checkAndStartStreaming, isStreaming, setupWebSocketHandlers]);

  // 캘리브레이션 종료 후 모니터 WebSocket 자동 재연결
  React.useEffect(() => {
    if (calibrationActive) return undefined;
    autoStartCheckedRef.current = false;
    const timer = setTimeout(() => {
      checkAndStartStreaming();
    }, 400);
    return () => clearTimeout(timer);
  }, [calibrationActive, checkAndStartStreaming]);

  // 스트리밍 이벤트 리스너
  React.useEffect(() => {
    console.log('[CameraSessions2] Component mounted, setting up event listeners');
    
    const handleStreamingStart = (event) => {
      console.log('[CameraSessions2] streamingStart event received:', event.detail);
      
      if (event.detail.cameraId !== cameraId) {
        console.log(`[CameraSessions2] Ignoring event for camera ${event.detail.cameraId}, waiting for camera ${cameraId}`);
        return;
      }

      console.log(`[CameraSessions2] Setting up WebSocket for camera ${cameraId}`);
      const websocket = event.detail.websocket;
      
      if (wsRef.current) {
        wsRef.current.close();
      }
      
      wsRef.current = websocket;
      setIsStreaming(true);
      autoStartCheckedRef.current = true;
      console.log(`[CameraSessions2] isStreaming set to true for camera ${cameraId}`);

      websocket.binaryType = 'blob';
      setupWebSocketHandlers(websocket);

      websocket.onerror = (error) => {
        console.error(`[CameraSessions2] WebSocket error for camera ${cameraId}:`, error);
        setIsStreaming(false);
      };

      websocket.onclose = (event) => {
        console.log(`[CameraSessions2] WebSocket closed for camera ${cameraId}, code: ${event.code}, reason: ${event.reason}`);
        setIsStreaming(false);
        wsRef.current = null;
      };
    };

    const handleStreamingStop = (event) => {
      console.log('[CameraSessions2] streamingStop event received:', event.detail);
      
      if (!event.detail || !event.detail.cameraId) {
        console.log('[CameraSessions2] Streaming stop event without cameraId, stopping all');
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
        setIsStreaming(false);
        return;
      }
      
      if (event.detail.cameraId !== cameraId) {
        console.log(`[CameraSessions2] Ignoring stop event for camera ${event.detail.cameraId}, waiting for camera ${cameraId}`);
        return;
      }

      console.log(`[CameraSessions2] Stopping streaming for camera ${cameraId}`);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsStreaming(false);
    };

    window.addEventListener('streamingStart', handleStreamingStart);
    window.addEventListener('streamingStop', handleStreamingStop);

    return () => {
      window.removeEventListener('streamingStart', handleStreamingStart);
      window.removeEventListener('streamingStop', handleStreamingStop);
      
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [cameraId, setupWebSocketHandlers]);

  return (
    <Card sx={{ height: '100%', boxShadow: 'none', border: '1px solid', borderColor: 'divider', bgcolor: 'background.default' }}>
      <CardContent sx={{ p: 1, height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5, flexShrink: 0, px: 0.5 }}>
          <Typography variant="subtitle2" component="div" sx={{ fontWeight: 600 }}>
            Camera 2 {calibrationActive ? '(Calibration)' : ''}
          </Typography>
          {showControls && (
            <FormControlLabel
              control={
                <Switch
                  checked={isStreaming || calibrationActive}
                  onChange={handleStreamingToggle}
                  color="primary"
                  size="small"
                  disabled={calibrationActive}
                />
              }
              label={calibrationActive ? 'Calibration' : isStreaming ? 'ON' : 'OFF'}
              labelPlacement="end"
              sx={{ m: 0 }}
            />
          )}
        </Box>
        <Box ref={containerRef} sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0 }}>
          {isStreaming || calibrationActive ? (
            <canvas
              ref={canvasRef}
              style={{
                width: `${displayWidth}px`,
                maxWidth: '100%',
                maxHeight: '100%',
                height: 'auto',
                backgroundColor: '#000',
                display: 'block',
                transform: `scale(${imageScale})`,
                transformOrigin: 'center',
              }}
            />
          ) : (
            <div
              style={{
                width: '100%',
                height: '100%',
                backgroundColor: '#000',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transform: `scale(${imageScale})`,
                transformOrigin: 'center',
              }}
            >
              <Typography variant="body1" color="white">
                스트리밍이 중지되었습니다
              </Typography>
            </div>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}
