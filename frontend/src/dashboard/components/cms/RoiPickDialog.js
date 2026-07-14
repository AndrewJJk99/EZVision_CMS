import * as React from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';

/**
 * 확대 이미지에서 ROI 박스를 드래그한 뒤 확인으로 확정.
 * label: 'A' | 'B'
 */
export default function RoiPickDialog({
  open,
  onClose,
  onConfirm,
  imageSrc,
  label = 'A',
  initialRoi = null,
}) {
  const imageBoxRef = React.useRef(null);
  const imageRef = React.useRef(null);
  const [drag, setDrag] = React.useState(null);
  const [draft, setDraft] = React.useState(null);
  const [, setLayoutTick] = React.useState(0);

  const color = label === 'B' ? '#ff5252' : '#00e676';

  React.useEffect(() => {
    if (open) {
      setDraft(initialRoi || null);
      setDrag(null);
    }
  }, [open, initialRoi]);

  React.useEffect(() => {
    if (!open) return undefined;
    const onResize = () => setLayoutTick((n) => n + 1);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [open]);

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
      if (!rect || !roi) return null;
      const x0 = Math.min(roi.x0, roi.x1);
      const x1 = Math.max(roi.x0, roi.x1);
      const y0 = Math.min(roi.y0, roi.y1);
      const y1 = Math.max(roi.y0, roi.y1);
      return {
        left: rect.left - rect.boxLeft + (x0 / rect.naturalWidth) * rect.width,
        top: rect.top - rect.boxTop + (y0 / rect.naturalHeight) * rect.height,
        width: ((x1 - x0) / rect.naturalWidth) * rect.width,
        height: ((y1 - y0) / rect.naturalHeight) * rect.height,
      };
    },
    [getContentRect],
  );

  const handleMouseDown = (event) => {
    const start = clientToNatural(event);
    if (!start) return;
    event.preventDefault();
    setDrag({ start, current: start });
  };

  const handleMouseMove = (event) => {
    if (!drag) return;
    const current = clientToNatural(event);
    if (!current) return;
    event.preventDefault();
    setDrag((prev) => ({ ...prev, current }));
  };

  const finishDrag = (event) => {
    if (!drag) return;
    event.preventDefault();
    const current = clientToNatural(event) || drag.current;
    const roi = {
      x0: Math.min(drag.start.x, current.x),
      y0: Math.min(drag.start.y, current.y),
      x1: Math.max(drag.start.x, current.x),
      y1: Math.max(drag.start.y, current.y),
    };
    setDrag(null);
    if (Math.abs(roi.x1 - roi.x0) >= 4 && Math.abs(roi.y1 - roi.y0) >= 4) {
      setDraft(roi);
    }
  };

  const handleConfirm = () => {
    if (!draft) return;
    onConfirm?.(draft);
    onClose?.();
  };

  const liveRoi = drag
    ? {
        x0: Math.min(drag.start.x, drag.current.x),
        y0: Math.min(drag.start.y, drag.current.y),
        x1: Math.max(drag.start.x, drag.current.x),
        y1: Math.max(drag.start.y, drag.current.y),
      }
    : null;
  const displayRoi = liveRoi || draft;
  const display = roiToDisplay(displayRoi);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={false}
      PaperProps={{
        sx: {
          m: 1,
          width: '96vw',
          maxWidth: '96vw',
          height: '94vh',
          maxHeight: '94vh',
          display: 'flex',
          flexDirection: 'column',
          bgcolor: '#111',
          color: 'grey.100',
        },
      }}
    >
      <DialogTitle sx={{ py: 1.25, pr: 6 }}>
        <Typography component="span" variant="h6" sx={{ fontWeight: 700, color }}>
          {label} 영역 선택
        </Typography>
        <Typography component="span" variant="body2" color="grey.400" sx={{ ml: 1.5 }}>
          드래그로 박스를 그린 뒤 확인을 누르세요
        </Typography>
        <IconButton
          aria-label="닫기"
          onClick={onClose}
          sx={{ position: 'absolute', right: 8, top: 8, color: 'grey.400' }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent
        sx={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          p: 1.5,
          pt: 0,
        }}
      >
        <Box
          ref={imageBoxRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={finishDrag}
          onMouseLeave={finishDrag}
          sx={{
            flex: 1,
            minHeight: 0,
            width: '100%',
            bgcolor: '#000',
            borderRadius: 1,
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            cursor: 'crosshair',
            userSelect: 'none',
          }}
        >
          {imageSrc ? (
            <>
              <img
                ref={imageRef}
                src={imageSrc}
                alt={`roi-${label}`}
                draggable={false}
                onLoad={() => setLayoutTick((n) => n + 1)}
                style={{
                  maxWidth: '100%',
                  maxHeight: '100%',
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  display: 'block',
                }}
              />
              {display && (
                <Box
                  sx={{
                    position: 'absolute',
                    left: display.left,
                    top: display.top,
                    width: display.width,
                    height: display.height,
                    border: `2px ${liveRoi ? 'dashed' : 'solid'} ${color}`,
                    bgcolor: `${color}22`,
                    pointerEvents: 'none',
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      position: 'absolute',
                      left: 4,
                      top: -22,
                      color,
                      fontWeight: 700,
                      textShadow: '0 0 4px #000',
                    }}
                  >
                    {label}
                  </Typography>
                </Box>
              )}
            </>
          ) : (
            <Typography color="grey.500">이미지가 없습니다</Typography>
          )}
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 2, py: 1.5, gap: 1 }}>
        {draft && (
          <Typography variant="caption" color="grey.400" sx={{ mr: 'auto' }}>
            ({draft.x0}, {draft.y0}) – ({draft.x1}, {draft.y1})
          </Typography>
        )}
        <Button onClick={onClose} color="inherit">
          취소
        </Button>
        <Button
          variant="outlined"
          color="inherit"
          disabled={!draft}
          onClick={() => {
            setDraft(null);
            setDrag(null);
          }}
        >
          다시 그리기
        </Button>
        <Button
          variant="contained"
          onClick={handleConfirm}
          disabled={!draft}
          sx={{ bgcolor: color, color: '#000', '&:hover': { bgcolor: color, filter: 'brightness(0.9)' } }}
        >
          확인
        </Button>
      </DialogActions>
    </Dialog>
  );
}
