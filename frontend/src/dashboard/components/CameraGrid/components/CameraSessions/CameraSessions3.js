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

export default function CameraSessions3({
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
  const cameraId = 3;
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

  // 화면 크기에 따라 표시 너비 계산 (활성화된 카메라 개수에 비례)
  const calculateDisplayWidth = React.useCallback(() => {
    // 활성화된 카메라 개수에 따라 화면 너비를 나눔
    const windowWidth = window.innerWidth;
    const currentCameraCount = activeCameraCountRef.current || 1;  // 최소 1개
    
    // 카메라 개수에 따라 너비 비율 조정
    let widthRatio = 1.0;  // 기본 100%
    let maxWidth = windowWidth;  // 화면 너비 전체를 최대값으로 설정
    
    // 1개일 때는 비율을 줄여서 너무 꽉 차지 않도록 함
    if (currentCameraCount === 1) {
      widthRatio = 0.75;  // 75% 사용
      maxWidth = 1200;  // 최대 너비 제한
    }
    
    const availableWidth = windowWidth * widthRatio;
    const calculatedWidth = Math.floor(availableWidth / currentCameraCount);
    // 최소 300px로 제한
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
        
        // 현재 Canvas에 이미지가 있는지 확인
        if (canvas.width > 0 && canvas.height > 0) {
          // 현재 이미지의 비율 유지
          const aspectRatio = canvas.height / canvas.width;
          
          // 활성화된 카메라 개수에 따라 새 크기 계산
          const windowWidth = window.innerWidth;
          
          // 카메라 개수에 따라 너비 비율 조정
          let widthRatio = 1.0;  // 기본 100%
          let maxWidth = windowWidth;  // 화면 너비 전체를 최대값으로 설정
          
          // 1개일 때는 비율을 줄여서 너무 꽉 차지 않도록 함
          if (activeCameraCount === 1) {
            widthRatio = 0.75;  // 75% 사용
            maxWidth = 1200;  // 최대 너비 제한
          }
          
          const availableWidth = windowWidth * widthRatio;
          const calculatedWidth = Math.floor(availableWidth / activeCameraCount);
          const minWidth = 300;
          let finalWidth = Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
          let finalHeight = finalWidth * aspectRatio;
          
          // 부모 컨테이너의 높이도 고려하여 크기 조정
          const parentBox = containerRef.current || canvas.parentElement;
          if (parentBox) {
            const parentHeight = parentBox.clientHeight || parentHeightRef.current;
            
            // 부모 컨테이너 높이를 최대한 활용 (여백 최소화)
            if (parentHeight) {
              const heightBasedWidth = Math.floor(parentHeight / aspectRatio);
              // 너비 기준과 높이 기준 중 더 작은 값을 사용하여 컨테이너를 넘지 않도록 함
              if (heightBasedWidth < finalWidth) {
                finalWidth = heightBasedWidth;
                finalHeight = finalWidth * aspectRatio;
              } else {
                // 너비 기준이 더 작으면 높이를 조정
                if (finalHeight > parentHeight) {
                  finalWidth = Math.floor(parentHeight / aspectRatio);
                  finalHeight = finalWidth * aspectRatio;
                }
              }
              
              parentHeightRef.current = parentHeight;
            }
          }
          
          // 현재 Canvas 내용을 임시로 저장
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          
          // Canvas 크기 변경
          canvas.width = finalWidth;
          canvas.height = finalHeight;
          
          // 임시 Canvas에 원본 이미지 그리기
          const tempCanvas = document.createElement('canvas');
          tempCanvas.width = imageData.width;
          tempCanvas.height = imageData.height;
          const tempCtx = tempCanvas.getContext('2d');
          tempCtx.putImageData(imageData, 0, 0);
          
          // 새 크기로 스케일링하여 다시 그리기
          ctx.drawImage(tempCanvas, 0, 0, finalWidth, finalHeight);
        } else {
          // Canvas가 비어있으면 크기만 설정 (다음 프레임이 올 때 자동으로 적용됨)
          // 활성화된 카메라 개수에 따라 새 크기 계산
          const windowWidth = window.innerWidth;
          
          // 카메라 개수에 따라 너비 비율 조정
          let widthRatio = 1.0;  // 기본 100%
          let maxWidth = windowWidth;  // 화면 너비 전체를 최대값으로 설정
          
          // 1개일 때는 비율을 줄여서 너무 꽉 차지 않도록 함
          if (activeCameraCount === 1) {
            widthRatio = 0.75;  // 75% 사용
            maxWidth = 1200;  // 최대 너비 제한
          }
          
          const availableWidth = windowWidth * widthRatio;
          const calculatedWidth = Math.floor(availableWidth / activeCameraCount);
          const minWidth = 300;
          let finalWidth = Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
          const aspectRatio = 0.75; // 4:3 비율
          let finalHeight = finalWidth * aspectRatio;
          
          // 부모 컨테이너의 높이도 고려하여 크기 조정
          const parentBox = containerRef.current || canvas.parentElement;
          if (parentBox) {
            const parentHeight = parentBox.clientHeight || parentHeightRef.current;
            
            // 부모 컨테이너 높이를 최대한 활용 (여백 최소화)
            if (parentHeight) {
              const heightBasedWidth = Math.floor(parentHeight / aspectRatio);
              // 너비 기준과 높이 기준 중 더 작은 값을 사용하여 컨테이너를 넘지 않도록 함
              if (heightBasedWidth < finalWidth) {
                finalWidth = heightBasedWidth;
                finalHeight = finalWidth * aspectRatio;
              } else {
                // 너비 기준이 더 작으면 높이를 조정
                if (finalHeight > parentHeight) {
                  finalWidth = Math.floor(parentHeight / aspectRatio);
                  finalHeight = finalWidth * aspectRatio;
                }
              }
              
              parentHeightRef.current = parentHeight;
            }
          }
          
          // 기본 비율로 크기 설정 (4:3)
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
      displayWidthRef.current = newWidth;  // ref도 업데이트
    };

    // 초기 크기 설정
    const initialWidth = calculateDisplayWidth();
    setDisplayWidth(initialWidth);
    displayWidthRef.current = initialWidth;  // ref도 초기화

    // 리사이즈 이벤트 리스너 등록
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [calculateDisplayWidth]);

  // WebSocket 핸들러 설정 함수
  const setupWebSocketHandlers = React.useCallback((websocket) => {
    websocket.onmessage = (messageEvent) => {
      if (calibrationActiveRef.current) return;

      const canvas = canvasRef.current;
      if (!canvas) {
        console.warn('[CameraSessions3] Canvas ref is null');
        return;
      }

      // Blob 또는 ArrayBuffer 처리
      let blob;
      if (messageEvent.data instanceof Blob) {
        blob = messageEvent.data;
      } else if (messageEvent.data instanceof ArrayBuffer) {
        blob = new Blob([messageEvent.data], { type: 'image/jpeg' });
      } else {
        console.warn('[CameraSessions3] Unknown data type received:', typeof messageEvent.data);
        return;
      }
      
      // Blob을 Image 객체로 변환하여 Canvas에 그리기
      const imageUrl = URL.createObjectURL(blob);
      const img = new Image();
      
      img.onload = () => {
        const ctx = canvas.getContext('2d');
        
        // Canvas 크기 설정 (비율 유지) - 최신 활성화된 카메라 개수로 실시간 계산
        const aspectRatio = img.height / img.width;
        // 활성화된 카메라 개수가 변경되었을 수 있으므로 실시간으로 계산
        const windowWidth = window.innerWidth;
        const currentCameraCount = activeCameraCountRef.current || 1;
        
        // 카메라 개수에 따라 너비 비율 조정
        let widthRatio = 1.0;  // 기본 100%
        let maxWidth = windowWidth;  // 화면 너비 전체를 최대값으로 설정
        
        // 1개일 때는 비율을 줄여서 너무 꽉 차지 않도록 함
        if (currentCameraCount === 1) {
          widthRatio = 0.75;  // 75% 사용
          maxWidth = 1200;  // 최대 너비 제한
        } else if (currentCameraCount === 4) {
          widthRatio = 0.95;   // 4개일 때 95% 사용
          maxWidth = 1400;      // 4개일 때 최대 너비 증가
        } else if (currentCameraCount === 3) {
          widthRatio = 0.92;   // 3개일 때 92% 사용
          maxWidth = 1200;      // 3개일 때 최대 너비 증가
        }
        
        const availableWidth = windowWidth * widthRatio;
        const calculatedWidth = Math.floor(availableWidth / currentCameraCount);
        const minWidth = 300;
        let currentDisplayWidth = Math.max(minWidth, Math.min(maxWidth, calculatedWidth));
        let calculatedHeight = currentDisplayWidth * aspectRatio;
        
        // 부모 컨테이너의 높이도 고려하여 크기 조정
        const parentBox = containerRef.current || canvas.parentElement;
        
        if (parentBox) {
          const parentHeight = parentBox.clientHeight || parentHeightRef.current;
          
          // 부모 컨테이너 높이를 최대한 활용 (여백 최소화)
          // 높이 기준으로 크기를 계산하여 부모 컨테이너를 최대한 채움
          if (parentHeight) {
            const heightBasedWidth = Math.floor(parentHeight / aspectRatio);
            // 너비 기준과 높이 기준 중 더 작은 값을 사용하여 컨테이너를 넘지 않도록 함
            if (heightBasedWidth < currentDisplayWidth) {
              currentDisplayWidth = heightBasedWidth;
              calculatedHeight = currentDisplayWidth * aspectRatio;
            } else {
              // 너비 기준이 더 작으면 높이를 조정
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
        
        // 이미지 그리기
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        
        // 메모리 정리
        URL.revokeObjectURL(imageUrl);
      };
      
      img.onerror = (error) => {
        console.error('[CameraSessions3] Error loading image:', error);
        URL.revokeObjectURL(imageUrl);
      };
      
      img.src = imageUrl;
    };
  }, []);  // displayWidth 의존성 제거 (ref 사용)

  // 수동 스트리밍 토글 핸들러
  const handleStreamingToggle = React.useCallback(async (event) => {
    const shouldStream = event.target.checked;
    manualToggleRef.current = true; // 수동 토글 플래그 설정
    
    if (shouldStream) {
      // 스트리밍 시작
      try {
        // 카메라 상태 확인
        const statusResponse = await getCameraStatus(cameraIdBackend);
        const status = statusResponse?.status;
        
        if (!status || !status.is_running) {
          alert(`카메라 ${cameraId}가 그래빙 중이 아닙니다. 먼저 "Start Grabbing" 버튼을 클릭해주세요.`);
          return;
        }
        
        // 기존 연결이 있으면 닫기
        if (wsRef.current) {
          wsRef.current.close();
        }
        
        // WebSocket 연결 시작
        const newWs = new WebSocket(getCameraWsUrl(cameraIdBackend));
        
        newWs.onopen = () => {
          console.log(`[CameraSessions3] Manual WebSocket connected for camera ${cameraId}`);
          wsRef.current = newWs;
          setIsStreaming(true);
          autoStartCheckedRef.current = true;
          
          // WebSocket 바이너리 타입 설정
          newWs.binaryType = 'blob';
          
          // 이미지 수신 핸들러 설정
          setupWebSocketHandlers(newWs);
        };
        
        newWs.onerror = (error) => {
          console.error(`[CameraSessions3] Manual WebSocket error for camera ${cameraId}:`, error);
          setIsStreaming(false);
          autoStartCheckedRef.current = false;
          manualToggleRef.current = false;
        };
        
        newWs.onclose = (event) => {
          console.log(`[CameraSessions3] Manual WebSocket closed for camera ${cameraId}, code: ${event.code}`);
          wsRef.current = null;
          setIsStreaming(false);
          autoStartCheckedRef.current = false;
          manualToggleRef.current = false;
        };
      } catch (error) {
        console.error(`[CameraSessions3] Error starting manual streaming:`, error);
        setIsStreaming(false);
        manualToggleRef.current = false;
      }
    } else {
      // 스트리밍 중지
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
    // 수동 토글이 활성화되어 있거나 이미 자동 시작을 시도했거나 스트리밍 중이면 스킵
    if (manualToggleRef.current || autoStartCheckedRef.current || isStreaming || wsRef.current) {
      return;
    }

    try {
      console.log(`[CameraSessions3] Checking camera ${cameraId} status for auto-start`);
      const statusResponse = await getCameraStatus(cameraIdBackend);
      const status = statusResponse?.status;
      
      if (status && status.is_running) {
        console.log(`[CameraSessions3] Camera ${cameraId} is running, starting auto-streaming`);
        autoStartCheckedRef.current = true;
        
        // WebSocket 연결 시작
        const newWs = new WebSocket(getCameraWsUrl(cameraIdBackend));
        
        newWs.onopen = () => {
          console.log(`[CameraSessions3] Auto-WebSocket connected for camera ${cameraId}`);
          wsRef.current = newWs;
          setIsStreaming(true);
          
          // WebSocket 바이너리 타입 설정
          newWs.binaryType = 'blob';
          
          // 이미지 수신 핸들러 설정
          setupWebSocketHandlers(newWs);
        };
        
        newWs.onerror = (error) => {
          console.error(`[CameraSessions3] Auto-WebSocket error for camera ${cameraId}:`, error);
          autoStartCheckedRef.current = false;
        };
        
        newWs.onclose = (event) => {
          console.log(`[CameraSessions3] Auto-WebSocket closed for camera ${cameraId}, code: ${event.code}`);
          wsRef.current = null;
          setIsStreaming(false);
          autoStartCheckedRef.current = false;
        };
      } else {
        console.log(`[CameraSessions3] Camera ${cameraId} is not running, skipping auto-start`);
      }
    } catch (error) {
      console.error(`[CameraSessions3] Error checking camera status:`, error);
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

  // 스트리밍 시작 이벤트 리스너
  React.useEffect(() => {
    console.log('[CameraSessions3] Component mounted, setting up event listeners');
    
    const handleStreamingStart = (event) => {
      console.log('[CameraSessions3] streamingStart event received:', event.detail);
      
      // 카메라 3번만 처리
      if (event.detail.cameraId !== cameraId) {
        console.log(`[CameraSessions3] Ignoring event for camera ${event.detail.cameraId}, waiting for camera ${cameraId}`);
        return;
      }

      console.log(`[CameraSessions3] Setting up WebSocket for camera ${cameraId}`);
      const websocket = event.detail.websocket;
      
      // 기존 연결이 있으면 닫기
      if (wsRef.current) {
        wsRef.current.close();
      }
      
      wsRef.current = websocket;
      setIsStreaming(true);
      autoStartCheckedRef.current = true; // 수동 시작으로 표시
      console.log(`[CameraSessions3] isStreaming set to true for camera ${cameraId}`);

      // WebSocket 바이너리 타입 설정 (Blob으로 받기)
      websocket.binaryType = 'blob';

      // WebSocket 핸들러 설정
      setupWebSocketHandlers(websocket);

      websocket.onerror = (error) => {
        console.error(`[CameraSessions3] WebSocket error for camera ${cameraId}:`, error);
        setIsStreaming(false);
      };

      websocket.onclose = (event) => {
        console.log(`[CameraSessions3] WebSocket closed for camera ${cameraId}, code: ${event.code}, reason: ${event.reason}`);
        setIsStreaming(false);
        wsRef.current = null;
      };
    };

    // 스트리밍 중지 이벤트 리스너
    const handleStreamingStop = (event) => {
      console.log('[CameraSessions3] streamingStop event received:', event.detail);
      
      // detail이 없거나 cameraId가 없으면 모든 카메라에 대해 중지 (언마운트 시 등)
      if (!event.detail || !event.detail.cameraId) {
        console.log('[CameraSessions3] Streaming stop event without cameraId, stopping all');
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
        setIsStreaming(false);
        return;
      }
      
      // 카메라 3번만 처리
      if (event.detail.cameraId !== cameraId) {
        console.log(`[CameraSessions3] Ignoring stop event for camera ${event.detail.cameraId}, waiting for camera ${cameraId}`);
        return;
      }

      console.log(`[CameraSessions3] Stopping streaming for camera ${cameraId}`);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsStreaming(false);
    };

    // 이벤트 리스너 등록
    window.addEventListener('streamingStart', handleStreamingStart);
    window.addEventListener('streamingStop', handleStreamingStop);

    // 클린업
    return () => {
      window.removeEventListener('streamingStart', handleStreamingStart);
      window.removeEventListener('streamingStop', handleStreamingStop);
      
      // 컴포넌트 언마운트 시 WebSocket 연결 종료
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
            Camera 3 {calibrationActive ? '(Calibration)' : ''}
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
