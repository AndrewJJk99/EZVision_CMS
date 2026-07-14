import * as React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Dialog from '@mui/material/Dialog';
import IconButton from '@mui/material/IconButton';
import Button from '@mui/material/Button';
import CloseIcon from '@mui/icons-material/Close';

export default function ResultImageCard({
  resultImage,
  originalImage = null,
  crop = null,
  emptyHint = '"캡처 & 검출"을 누르면 결과가 표시됩니다',
  fill = false,
  maxHeight = '70vh',
  minHeight = 320,
  roiSelection = null,
}) {
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [showOriginal, setShowOriginal] = React.useState(false);
  const imageBoxRef = React.useRef(null);
  const imageRef = React.useRef(null);
  const [drag, setDrag] = React.useState(null);

  const canToggle = Boolean(originalImage && resultImage && originalImage !== resultImage);
  const displayImage = showOriginal && originalImage ? originalImage : resultImage;
  // 확대본(crop)을 볼 때는 ROI 좌표(원본 기준)를 crop 오프셋만큼 보정
  const cropOffset = !showOriginal && crop ? { x: crop.x0, y: crop.y0 } : { x: 0, y: 0 };

  React.useEffect(() => {
    setShowOriginal(false);
  }, [resultImage, originalImage]);

  const roiEnabled = Boolean(roiSelection?.enabled && roiSelection?.active && displayImage);

  const adjustRoi = React.useCallback(
    (roi) => {
      if (!roi) return null;
      return {
        x0: roi.x0 - cropOffset.x,
        y0: roi.y0 - cropOffset.y,
        x1: roi.x1 - cropOffset.x,
        y1: roi.y1 - cropOffset.y,
      };
    },
    [cropOffset.x, cropOffset.y],
  );

  const getContentRect = React.useCallback(() => {
    const img = imageRef.current;
    const box = imageBoxRef.current;
    if (!img || !box || !img.naturalWidth || !img.naturalHeight) return null;
    const imgRect = img.getBoundingClientRect();
    const boxRect = box.getBoundingClientRect();
    const imageAspect = img.naturalWidth / img.naturalHeight;
    const elementAspect = imgRect.width / imgRect.height;
    let width = imgRect.width;
    let height = imgRect.height;
    let left = imgRect.left;
    let top = imgRect.top;
    if (elementAspect > imageAspect) {
      width = imgRect.height * imageAspect;
      left = imgRect.left + (imgRect.width - width) / 2;
    } else {
      height = imgRect.width / imageAspect;
      top = imgRect.top + (imgRect.height - height) / 2;
    }
    return {
      left,
      top,
      width,
      height,
      boxLeft: boxRect.left,
      boxTop: boxRect.top,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
    };
  }, []);

  const clientToNatural = React.useCallback(
    (event) => {
      const rect = getContentRect();
      if (!rect) return null;
      const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
      const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
      return {
        x: Math.round((x / rect.width) * rect.naturalWidth),
        y: Math.round((y / rect.height) * rect.naturalHeight),
      };
    },
    [getContentRect],
  );

  const roiToDisplay = React.useCallback(
    (roi) => {
      const rect = getContentRect();
      const adj = adjustRoi(roi);
      if (!rect || !adj) return null;
      const x0 = Math.min(adj.x0, adj.x1);
      const x1 = Math.max(adj.x0, adj.x1);
      const y0 = Math.min(adj.y0, adj.y1);
      const y1 = Math.max(adj.y0, adj.y1);
      return {
        left: rect.left - rect.boxLeft + (x0 / rect.naturalWidth) * rect.width,
        top: rect.top - rect.boxTop + (y0 / rect.naturalHeight) * rect.height,
        width: ((x1 - x0) / rect.naturalWidth) * rect.width,
        height: ((y1 - y0) / rect.naturalHeight) * rect.height,
      };
    },
    [getContentRect, adjustRoi],
  );

  const handleMouseDown = (event) => {
    if (!roiEnabled) return;
    const start = clientToNatural(event);
    if (!start) return;
    event.preventDefault();
    event.stopPropagation();
    setDrag({ start, current: start });
  };

  const handleMouseMove = (event) => {
    if (!roiEnabled || !drag) return;
    const current = clientToNatural(event);
    if (!current) return;
    event.preventDefault();
    setDrag((prev) => ({ ...prev, current }));
  };

  const finishDrag = (event) => {
    if (!roiEnabled || !drag) return;
    event.preventDefault();
    event.stopPropagation();
    const current = clientToNatural(event) || drag.current;
    const roi = {
      x0: Math.min(drag.start.x, current.x),
      y0: Math.min(drag.start.y, current.y),
      x1: Math.max(drag.start.x, current.x),
      y1: Math.max(drag.start.y, current.y),
    };
    setDrag(null);
    if (Math.abs(roi.x1 - roi.x0) >= 4 && Math.abs(roi.y1 - roi.y0) >= 4) {
      roiSelection?.onChange?.(roiSelection.active, roi);
    }
  };

  const imageBoxSx = fill
    ? {
        flex: 1,
        minHeight: 160,
        height: '100%',
      }
    : {
        minHeight,
        maxHeight,
      };

  const imageStyle = fill
    ? { width: '100%', height: '100%', display: 'block', objectFit: 'contain' }
    : { maxWidth: '100%', maxHeight, display: 'block', objectFit: 'contain' };

  return (
    <>
      <Card
        sx={{
          minWidth: 0,
          overflow: 'hidden',
          ...(fill && {
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
          }),
        }}
      >
        <CardContent
          sx={{
            minWidth: 0,
            ...(fill && {
              flex: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              pb: '16px !important',
            }),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexShrink: 0 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, flex: 1 }}>
              결과 이미지 (노란 점 = 검출된 레이저 선)
              {displayImage && (
                <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                  · 클릭하면 확대
                </Typography>
              )}
            </Typography>
            {canToggle && (
              <Button
                size="small"
                variant="outlined"
                onClick={() => setShowOriginal((v) => !v)}
                sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}
              >
                {showOriginal ? '레이저 확대' : '원본 보기'}
              </Button>
            )}
          </Box>
          <Box
            ref={imageBoxRef}
            onClick={() => displayImage && !roiEnabled && setPreviewOpen(true)}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={finishDrag}
            onMouseLeave={finishDrag}
            sx={{
              width: '100%',
              bgcolor: '#000',
              borderRadius: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              position: 'relative',
              cursor: roiEnabled ? 'crosshair' : displayImage ? 'zoom-in' : 'default',
              ...imageBoxSx,
            }}
          >
            {displayImage ? (
              <>
                <img ref={imageRef} src={displayImage} alt="result" style={imageStyle} draggable={false} />
                {['a', 'b'].map((key) => {
                  const roi = roiSelection?.rois?.[key];
                  const display = roiToDisplay(roi);
                  if (!display) return null;
                  const color = key === 'a' ? '#00e676' : '#ff5252';
                  return (
                    <Box
                      key={key}
                      sx={{
                        position: 'absolute',
                        left: display.left,
                        top: display.top,
                        width: display.width,
                        height: display.height,
                        border: `2px solid ${color}`,
                        bgcolor: `${color}22`,
                        pointerEvents: 'none',
                      }}
                    >
                      <Typography
                        variant="caption"
                        sx={{ position: 'absolute', left: 3, top: -20, color, fontWeight: 700 }}
                      >
                        {key.toUpperCase()}
                      </Typography>
                    </Box>
                  );
                })}
                {drag &&
                  (() => {
                    const roi = {
                      x0: Math.min(drag.start.x, drag.current.x),
                      y0: Math.min(drag.start.y, drag.current.y),
                      x1: Math.max(drag.start.x, drag.current.x),
                      y1: Math.max(drag.start.y, drag.current.y),
                    };
                    const display = roiToDisplay(roi);
                    if (!display) return null;
                    const color = roiSelection.active === 'a' ? '#00e676' : '#ff5252';
                    return (
                      <Box
                        sx={{
                          position: 'absolute',
                          left: display.left,
                          top: display.top,
                          width: display.width,
                          height: display.height,
                          border: `2px dashed ${color}`,
                          bgcolor: `${color}18`,
                          pointerEvents: 'none',
                        }}
                      />
                    );
                  })()}
              </>
            ) : (
              <Typography variant="body2" color="grey.500">
                {emptyHint}
              </Typography>
            )}
          </Box>
        </CardContent>
      </Card>

      <Dialog
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        maxWidth={false}
        PaperProps={{
          sx: {
            bgcolor: '#111',
            m: 1,
            maxWidth: '96vw',
            maxHeight: '96vh',
            overflow: 'hidden',
          },
        }}
      >
        <IconButton
          aria-label="닫기"
          onClick={() => setPreviewOpen(false)}
          sx={{ position: 'absolute', right: 8, top: 8, color: 'grey.300', zIndex: 1 }}
        >
          <CloseIcon />
        </IconButton>
        {canToggle && (
          <Button
            size="small"
            variant="contained"
            onClick={(e) => {
              e.stopPropagation();
              setShowOriginal((v) => !v);
            }}
            sx={{ position: 'absolute', left: 12, top: 12, zIndex: 1 }}
          >
            {showOriginal ? '레이저 확대' : '원본 보기'}
          </Button>
        )}
        <Box
          onClick={() => setPreviewOpen(false)}
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            p: 2,
            pt: 5,
            boxSizing: 'border-box',
            maxWidth: '96vw',
            maxHeight: '96vh',
            cursor: 'zoom-out',
          }}
        >
          {displayImage && (
            <img
              src={displayImage}
              alt="result preview"
              style={{ maxWidth: '92vw', maxHeight: '88vh', display: 'block', objectFit: 'contain' }}
            />
          )}
        </Box>
      </Dialog>
    </>
  );
}
