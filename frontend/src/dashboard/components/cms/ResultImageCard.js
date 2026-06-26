import * as React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Dialog from '@mui/material/Dialog';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';

export default function ResultImageCard({
  resultImage,
  emptyHint = '"캡처 & 검출"을 누르면 결과가 표시됩니다',
  fill = false,
  maxHeight = '70vh',
  minHeight = 320,
}) {
  const [previewOpen, setPreviewOpen] = React.useState(false);

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
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1, flexShrink: 0 }}>
            결과 이미지 (노란 점 = 검출된 레이저 선)
            {resultImage && (
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                · 클릭하면 확대
              </Typography>
            )}
          </Typography>
          <Box
            onClick={() => resultImage && setPreviewOpen(true)}
            sx={{
              width: '100%',
              bgcolor: '#000',
              borderRadius: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              cursor: resultImage ? 'zoom-in' : 'default',
              ...imageBoxSx,
            }}
          >
            {resultImage ? (
              <img src={resultImage} alt="result" style={imageStyle} />
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
          {resultImage && (
            <img
              src={resultImage}
              alt="result preview"
              style={{ maxWidth: '92vw', maxHeight: '88vh', display: 'block', objectFit: 'contain' }}
            />
          )}
        </Box>
      </Dialog>
    </>
  );
}
