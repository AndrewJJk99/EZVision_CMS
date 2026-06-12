import os
import sys
import threading
import time
import asyncio
import logging
import tempfile
from ctypes import *
from ctypes import cdll

import httpx
import numpy as np
import cv2

from utils.MvCameraControl_class import *
from utils.MvErrorDefine_const import *
from utils.CameraParams_header import *

# 프로젝트 경로 추가
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

logger = logging.getLogger(__name__)

# HB (High Bandwidth) 포맷 리스트 (RAW 저장 시 디코딩 필요)
HB_format_list = [
    PixelType_Gvsp_HB_Mono8,
    PixelType_Gvsp_HB_Mono10,
    PixelType_Gvsp_HB_Mono10_Packed,
    PixelType_Gvsp_HB_Mono12,
    PixelType_Gvsp_HB_Mono12_Packed,
    PixelType_Gvsp_HB_Mono16,
    PixelType_Gvsp_HB_BayerGR8,
    PixelType_Gvsp_HB_BayerRG8,
    PixelType_Gvsp_HB_BayerGB8,
    PixelType_Gvsp_HB_BayerBG8,
    PixelType_Gvsp_HB_BayerRBGG8,
    PixelType_Gvsp_HB_BayerGR10,
    PixelType_Gvsp_HB_BayerRG10,
    PixelType_Gvsp_HB_BayerGB10,
    PixelType_Gvsp_HB_BayerBG10,
    PixelType_Gvsp_HB_BayerGR12,
    PixelType_Gvsp_HB_BayerRG12,
    PixelType_Gvsp_HB_BayerGB12,
    PixelType_Gvsp_HB_BayerBG12,
    PixelType_Gvsp_HB_BayerGR10_Packed,
    PixelType_Gvsp_HB_BayerRG10_Packed,
    PixelType_Gvsp_HB_BayerGB10_Packed,
    PixelType_Gvsp_HB_BayerBG10_Packed,
    PixelType_Gvsp_HB_BayerGR12_Packed,
    PixelType_Gvsp_HB_BayerRG12_Packed,
    PixelType_Gvsp_HB_BayerGB12_Packed,
    PixelType_Gvsp_HB_BayerBG12_Packed,
    PixelType_Gvsp_HB_YUV422_Packed,
    PixelType_Gvsp_HB_YUV422_YUYV_Packed,
    PixelType_Gvsp_HB_RGB8_Packed,
    PixelType_Gvsp_HB_BGR8_Packed,
    PixelType_Gvsp_HB_RGBA8_Packed,
    PixelType_Gvsp_HB_BGRA8_Packed,
    PixelType_Gvsp_HB_RGB16_Packed,
    PixelType_Gvsp_HB_BGR16_Packed,
    PixelType_Gvsp_HB_RGBA16_Packed,
    PixelType_Gvsp_HB_BGRA16_Packed
]


class CameraOperation:
    """제조사 예제 방식의 카메라 운영 클래스 (비동기 지원 추가)"""
    
    def __init__(self, obj_cam=None, st_device_list=None, n_connect_num=0):
        self.obj_cam = obj_cam
        self.st_device_list = st_device_list
        self.n_connect_num = n_connect_num
        self.camera_id = n_connect_num  # 백엔드 슬롯 ID (0-3), UI 카메라 번호는 +1
        self.device_ip = None
        
        # 상태 플래그
        self.b_open_device = False
        self.b_start_grabbing = False
        self.b_thread_opened = False
        self.b_saving = False  # 저장 중 플래그 (스트리밍 일시 중지용)
        
        # 프레임 버퍼
        self.st_frame_info = MV_FRAME_OUT_INFO_EX()
        self.buf_save_image = None
        self.buf_save_image_len = 0
        self.buf_lock = threading.Lock()  # 프레임 버퍼 접근 락
        
        # 스레드 관리
        self.h_thread_handle = None
        self.exit_flag = None
        
        # 통계
        self.frame_count = 0
        self.lost_frame_count = 0
    
    def to_hex_str(self, num):
        """에러 코드를 16진수 문자열로 변환"""
        chaDic = {10: 'a', 11: 'b', 12: 'c', 13: 'd', 14: 'e', 15: 'f'}
        hexStr = ""
        if num < 0:
            num = num + 2**32
        while num >= 16:
            digit = num % 16
            hexStr = chaDic.get(digit, str(digit)) + hexStr
            num //= 16
        hexStr = chaDic.get(num, str(num)) + hexStr
        return hexStr
    
    def open_device(self, device_info):
        """카메라 디바이스 열기"""
        if self.b_open_device:
            return 0
        
        try:
            # 핸들 생성
            self.obj_cam = MvCamera()
            ret = self.obj_cam.MV_CC_CreateHandle(device_info)
            if ret != 0:
                self.obj_cam.MV_CC_DestroyHandle()
                print(f"Camera {self.camera_id}: Create handle fail! ret[0x{ret:x}]")
                return ret
            
            # 디바이스 열기 (재시도 로직 포함)
            max_retries = 3
            retry_delay = 0.5
            open_success = False
            
            for retry in range(max_retries):
                ret = self.obj_cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
                if ret == 0:
                    open_success = True
                    break
                else:
                    if ret == 0x80000203:  # MV_E_ACCESS_DENIED
                        print(f"Camera {self.camera_id}: Open device fail (Access Denied). Retry {retry + 1}/{max_retries}...")
                        try:
                            self.obj_cam.MV_CC_DestroyHandle()
                        except:
                            pass
                        time.sleep(retry_delay)
                        # 새 핸들 생성
                        self.obj_cam = MvCamera()
                        ret = self.obj_cam.MV_CC_CreateHandle(device_info)
                        if ret != 0:
                            print(f"Camera {self.camera_id}: Create handle fail on retry! ret[0x{ret:x}]")
                            break
                    else:
                        print(f"Camera {self.camera_id}: Open device fail! ret[0x{ret:x}]")
                        if retry < max_retries - 1:
                            time.sleep(retry_delay)
            
            if not open_success:
                try:
                    self.obj_cam.MV_CC_DestroyHandle()
                except:
                    pass
                self.obj_cam = None
                self.b_open_device = False
                # OpenDevice 실패 후 CreateHandle만 성공한 경우 ret==0 이 될 수 있음
                return ret if ret != 0 else 0x80000203
            
            # GigE 카메라인 경우 패킷 크기 설정
            if device_info.nTLayerType == MV_GIGE_DEVICE:
                nPacketSize = self.obj_cam.MV_CC_GetOptimalPacketSize()
                if int(nPacketSize) > 0:
                    ret = self.obj_cam.MV_CC_SetIntValue("GevSCPSPacketSize", nPacketSize)
                    if ret != 0:
                        print(f"Camera {self.camera_id}: Warning: Set packet size fail! ret[0x{ret:x}]")
            
            self.b_open_device = True
            self.b_thread_opened = False
            if device_info.nTLayerType == MV_GIGE_DEVICE:
                nip1 = ((device_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
                nip2 = ((device_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
                nip3 = ((device_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
                nip4 = (device_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
                self.device_ip = f"{nip1}.{nip2}.{nip3}.{nip4}"
            print(
                f"Camera {self.camera_id} (UI: {self.camera_id + 1}) opened successfully"
                + (f" [IP: {self.device_ip}]" if self.device_ip else "")
            )
            return 0
            
        except Exception as e:
            print(f"Camera {self.camera_id}: Error opening device: {e}")
            if self.obj_cam:
                try:
                    self.obj_cam.MV_CC_DestroyHandle()
                except:
                    pass
                self.obj_cam = None
            return -1
    
    def set_feature(self, fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format):
        """카메라 설정 변경"""
        if not self.b_open_device:
            return None
        
        try:
            pixel_format_map = {
                1: 17301505, 2: 17825795, 3: 17825797, 4: 35127316,
                5: 35127317, 6: 34603058, 7: 34603039, 8: 17301513,
                9: 17825805, 10: 17563687, 11: 17825809, 12: 17563691
            }
            
            ret = self.obj_cam.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", fpsenable)
            if fpsenable == 1:
                ret = self.obj_cam.MV_CC_SetFloatValue("AcquisitionFrameRate", fps)
            
            ret = self.obj_cam.MV_CC_SetEnumValue("GainAuto", gainauto)
            if gainauto == 0:
                ret = self.obj_cam.MV_CC_SetFloatValue("Gain", gain)
            
            ret = self.obj_cam.MV_CC_SetFloatValue("ExposureTime", exposuretime)
            ret = self.obj_cam.MV_CC_SetIntValue("Width", width)
            ret = self.obj_cam.MV_CC_SetIntValue("Height", height)
            ret = self.obj_cam.MV_CC_SetEnumValue("PixelFormat", pixel_format_map[pixel_format])
            
            return True
            
        except Exception as e:
            print(f"Camera {self.camera_id}: Error setting features: {e}")
            return None
    
    def get_feature(self):
        """카메라 설정 조회"""
        if not self.b_open_device or self.obj_cam is None:
            print(f"Camera {self.camera_id}: Device not open, cannot get features")
            return None
        
        try:
            settings = {}
            stParam = MVCC_INTVALUE()
            
            ret = self.obj_cam.MV_CC_GetBoolValue("AcquisitionFrameRateEnable", stParam)
            if ret == 0:
                settings['AcquisitionFrameRateEnable'] = stParam.nCurValue
            
            stParam = MVCC_FLOATVALUE()
            ret = self.obj_cam.MV_CC_GetFloatValue("AcquisitionFrameRate", stParam)
            if ret == 0:
                settings['AcquisitionFrameRate'] = stParam.fCurValue
            
            ret = self.obj_cam.MV_CC_GetFloatValue("ResultingFrameRate", stParam)
            if ret == 0:
                settings['ResultingFrameRate'] = stParam.fCurValue
            
            stParam = MVCC_ENUMVALUE()
            ret = self.obj_cam.MV_CC_GetEnumValue("GainAuto", stParam)
            if ret == 0:
                settings['GainAuto'] = stParam.nCurValue
            
            stParam = MVCC_FLOATVALUE()
            ret = self.obj_cam.MV_CC_GetFloatValue("Gain", stParam)
            if ret == 0:
                settings['Gain'] = stParam.fCurValue
            
            ret = self.obj_cam.MV_CC_GetFloatValue("ExposureTime", stParam)
            if ret == 0:
                settings['ExposureTime'] = stParam.fCurValue
            
            stParam = MVCC_INTVALUE()
            ret = self.obj_cam.MV_CC_GetIntValue("Width", stParam)
            if ret == 0:
                settings['Width'] = stParam.nCurValue
            
            ret = self.obj_cam.MV_CC_GetIntValue("Height", stParam)
            if ret == 0:
                settings['Height'] = stParam.nCurValue
            
            stParam = MVCC_ENUMVALUE()
            ret = self.obj_cam.MV_CC_GetEnumValue("PixelFormat", stParam)
            if ret == 0:
                settings['PixelFormat'] = stParam.nCurValue
            
            return settings
            
        except Exception as e:
            print(f"Camera {self.camera_id}: Error getting features: {e}")
            return None
    
    def start_grabbing(self, n_index, win_handle):
        """그래빙 시작 (제조사 예제 방식)"""
        if not self.b_start_grabbing and self.b_open_device:
            ret = self.obj_cam.MV_CC_StartGrabbing()
            if ret != 0:
                self.b_start_grabbing = False
                return ret
            self.b_start_grabbing = True
            print(f"start grabbing {n_index} successfully!")
            try:
                self.exit_flag = threading.Event()
                self.h_thread_handle = threading.Thread(
                    target=CameraOperation.work_thread,
                    args=(self, n_index, win_handle, self.exit_flag)
                )
                self.h_thread_handle.start()
                self.b_thread_opened = True
            except TypeError:
                print('error: unable to start thread')
                self.b_start_grabbing = False
            return 0
        return MV_E_CALLORDER
    
    def stop_grabbing(self):
        """그래빙 중지 (제조사 예제 방식)"""
        if (self.b_start_grabbing is True) and (self.b_open_device is True):
            # 스레드 종료
            if self.b_thread_opened:
                self.exit_flag.set()
                self.h_thread_handle.join()
                self.b_thread_opened = False
            ret = self.obj_cam.MV_CC_StopGrabbing()
            if ret != 0:
                return ret
            self.b_start_grabbing = False
            return 0
        return MV_E_CALLORDER
    
    def close_device(self):
        """카메라 디바이스 닫기 (제조사 예제 방식)"""
        try:
            if self.obj_cam is None:
                self.b_open_device = False
                self.b_start_grabbing = False
                return 0

            if self.b_open_device:
                if self.b_thread_opened and self.exit_flag is not None:
                    self.exit_flag.set()
                    if self.h_thread_handle is not None:
                        self.h_thread_handle.join(timeout=3.0)
                    self.b_thread_opened = False
                if self.b_start_grabbing:
                    ret = self.obj_cam.MV_CC_StopGrabbing()
                    if ret != 0:
                        print(f"Camera {self.camera_id}: Stop grabbing fail! ret[0x{ret:x}]")
                    self.b_start_grabbing = False
                ret = self.obj_cam.MV_CC_CloseDevice()
                if ret != 0:
                    print(f"Camera {self.camera_id}: Close device fail! ret[0x{ret:x}]")

            self.obj_cam.MV_CC_DestroyHandle()
            self.obj_cam = None
            self.b_open_device = False
            return 0
        except Exception as e:
            print(f"Camera {self.camera_id}: Error closing device: {e}")
            self.obj_cam = None
            self.b_open_device = False
            self.b_start_grabbing = False
            return -1
    
    def work_thread(self, n_index, win_handle, exit_flag):
        """그래빙 스레드 함수 (제조사 예제 방식)"""
        stOutFrame = MV_FRAME_OUT()
        memset(byref(stOutFrame), 0, sizeof(stOutFrame))

        while not exit_flag.is_set():
            ret = self.obj_cam.MV_CC_GetImageBuffer(stOutFrame, 1000)
            if 0 == ret:
                # 이미지 및 이미지 정보 복사
                # 버퍼 락 획득
                self.buf_lock.acquire()
                try:
                    if self.buf_save_image_len < stOutFrame.stFrameInfo.nFrameLen:
                        if self.buf_save_image is not None:
                            del self.buf_save_image
                            self.buf_save_image = None
                        self.buf_save_image = (c_ubyte * stOutFrame.stFrameInfo.nFrameLen)()
                        self.buf_save_image_len = stOutFrame.stFrameInfo.nFrameLen

                    cdll.msvcrt.memcpy(byref(self.st_frame_info), byref(stOutFrame.stFrameInfo), sizeof(MV_FRAME_OUT_INFO_EX))
                    cdll.msvcrt.memcpy(byref(self.buf_save_image), stOutFrame.pBufAddr, self.st_frame_info.nFrameLen)
                finally:
                    self.buf_lock.release()

                # win_handle이 None이 아니면 Display 사용 (제조사 예제 방식)
                if win_handle is not None:
                    stDisplayParam = MV_DISPLAY_FRAME_INFO()
                    memset(byref(stDisplayParam), 0, sizeof(stDisplayParam))
                    stDisplayParam.hWnd = int(win_handle)
                    stDisplayParam.nWidth = stOutFrame.stFrameInfo.nWidth
                    stDisplayParam.nHeight = stOutFrame.stFrameInfo.nHeight
                    stDisplayParam.enPixelType = stOutFrame.stFrameInfo.enPixelType
                    stDisplayParam.pData = stOutFrame.pBufAddr
                    stDisplayParam.nDataLen = stOutFrame.stFrameInfo.nFrameLen
                    self.obj_cam.MV_CC_DisplayOneFrame(stDisplayParam)

                # 버퍼 해제
                self.obj_cam.MV_CC_FreeImageBuffer(stOutFrame)
            else:
                if ret != 0x8000000D:  # MV_E_NOOUTBUF는 너무 많이 출력되므로 제외
                    print(f"Camera[{n_index}]: no data, ret = {self.to_hex_str(ret)}")
                continue
    
    def get_frame_jpeg(self, stream_width=None, stream_height=None):
        """
        버퍼에서 JPEG로 변환 (제조사 save_bmp 방식 참고)
        
        Args:
            stream_width: 스트리밍용 너비 (None이면 원본 크기)
            stream_height: 스트리밍용 높이 (None이면 원본 크기)
        
        Returns:
            bytes: JPEG 이미지 데이터 (해상도 축소된 경우 축소된 크기)
        """
        if not self.b_open_device:
            return None
        
        try:
            # 락은 스냅샷 복사만 짧게 잡고, JPEG 변환은 락 밖에서 수행 (그래빙 스레드 블로킹 방지)
            self.buf_lock.acquire()
            try:
                if self.buf_save_image is None or self.st_frame_info.nFrameLen <= 0:
                    return None

                frame_len = self.st_frame_info.nFrameLen
                snap_info = MV_FRAME_OUT_INFO_EX()
                cdll.msvcrt.memcpy(byref(snap_info), byref(self.st_frame_info), sizeof(MV_FRAME_OUT_INFO_EX))
                snap_buf = (c_ubyte * frame_len)()
                cdll.msvcrt.memcpy(byref(snap_buf), self.buf_save_image, frame_len)
            finally:
                self.buf_lock.release()

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.close()

            stSaveParam = MV_SAVE_IMAGE_TO_FILE_PARAM_EX()
            stSaveParam.enPixelType = snap_info.enPixelType
            stSaveParam.nWidth = snap_info.nWidth
            stSaveParam.nHeight = snap_info.nHeight
            stSaveParam.nDataLen = frame_len
            stSaveParam.pData = cast(snap_buf, POINTER(c_ubyte))
            stSaveParam.enImageType = MV_Image_Jpeg
            stSaveParam.pcImagePath = create_string_buffer(temp_file.name.encode('ascii'))
            stSaveParam.iMethodValue = 1
            stSaveParam.nQuality = 90

            ret = self.obj_cam.MV_CC_SaveImageToFileEx(stSaveParam)

            if ret == 0:
                with open(temp_file.name, 'rb') as f:
                    jpeg_data = f.read()
                os.unlink(temp_file.name)

                if stream_width is not None and stream_height is not None:
                    try:
                        nparr = np.frombuffer(jpeg_data, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                        if img is not None:
                            resized_img = cv2.resize(
                                img, (stream_width, stream_height), interpolation=cv2.INTER_LINEAR
                            )
                            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                            _, jpeg_data = cv2.imencode('.jpg', resized_img, encode_param)
                            jpeg_data = jpeg_data.tobytes()
                    except Exception as resize_error:
                        print(
                            f"Camera {self.n_connect_num}: Error resizing image: {resize_error}, returning original"
                        )

                return jpeg_data

            print(f"Camera {self.n_connect_num}: Save image fail! ret[0x{ret:x}]")
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            return None
                
        except Exception as e:
            print(f"Camera {self.n_connect_num}: Error in get_frame_jpeg: {e}")
            return None
    
    def save_image(self, file_path, save_type=2, quality=99):
        """
        버퍼에서 이미지를 파일로 저장 (원본 사이즈)
        
        Args:
            file_path: 저장할 파일 경로 (확장자 포함)
            save_type: 저장 타입 (1=JPG, 2=BMP, 3=TIF, 4=PNG, 0=RAW)
            quality: JPG 품질 (50-99, 다른 포맷에서는 무시)
        
        Returns:
            0: 성공, 그 외: 에러 코드
        """
        if not self.buf_save_image or not self.b_open_device:
            print(f"Camera {self.camera_id}: No image buffer available or device not open")
            return -1
        
        # 저장 시작 플래그 설정 (스트리밍 일시 중지)
        self.b_saving = True
        
        try:
            self.buf_lock.acquire()
            try:
                if self.buf_save_image is None:
                    print(f"Camera {self.camera_id}: buf_save_image is None")
                    return -1
                
                # RAW 저장
                if save_type == 0:
                    result = self._save_raw(file_path)
                else:
                    # JPG/BMP/TIF/PNG 저장
                    result = self._save_non_raw_image(file_path, save_type, quality)
                
                return result
                    
            finally:
                self.buf_lock.release()
                # 저장 완료 플래그 해제 (스트리밍 재개)
                self.b_saving = False
                
        except Exception as e:
            print(f"Camera {self.camera_id}: Error in save_image: {e}")
            import traceback
            traceback.print_exc()
            # 에러 발생 시에도 플래그 해제
            self.b_saving = False
            return -1
    
    def _save_non_raw_image(self, file_path, save_type, quality):
        """비RAW 이미지 저장 (JPG/BMP/TIF/PNG)"""
        try:
            # 저장 타입에 따른 이미지 타입 및 확장자 결정
            if save_type == 1:
                mv_image_type = MV_Image_Jpeg
                if not file_path.lower().endswith(('.jpg', '.jpeg')):
                    file_path = file_path.rsplit('.', 1)[0] + '.jpg'
            elif save_type == 2:
                mv_image_type = MV_Image_Bmp
                if not file_path.lower().endswith('.bmp'):
                    file_path = file_path.rsplit('.', 1)[0] + '.bmp'
            elif save_type == 3:
                mv_image_type = MV_Image_Tif
                if not file_path.lower().endswith(('.tif', '.tiff')):
                    file_path = file_path.rsplit('.', 1)[0] + '.tif'
            else:  # save_type == 4
                mv_image_type = MV_Image_Png
                if not file_path.lower().endswith('.png'):
                    file_path = file_path.rsplit('.', 1)[0] + '.png'
            
            # 파일 경로 인코딩
            c_file_path = file_path.encode('ascii')
            
            # 저장 파라미터 설정
            stSaveParam = MV_SAVE_IMAGE_TO_FILE_PARAM_EX()
            stSaveParam.enPixelType = self.st_frame_info.enPixelType
            stSaveParam.nWidth = self.st_frame_info.nWidth
            stSaveParam.nHeight = self.st_frame_info.nHeight
            stSaveParam.nDataLen = self.st_frame_info.nFrameLen
            stSaveParam.pData = cast(self.buf_save_image, POINTER(c_ubyte))
            stSaveParam.enImageType = mv_image_type
            stSaveParam.pcImagePath = create_string_buffer(c_file_path)
            stSaveParam.iMethodValue = 1
            stSaveParam.nQuality = quality  # JPG: (50,99], 다른 포맷에서는 무시
            
            ret = self.obj_cam.MV_CC_SaveImageToFileEx(stSaveParam)
            
            if ret == 0:
                print(f"Camera {self.camera_id}: Image saved successfully to {file_path}")
            else:
                print(f"Camera {self.camera_id}: Save image fail! ret[0x{ret:x}]")
            
            return ret
            
        except Exception as e:
            print(f"Camera {self.camera_id}: Error in _save_non_raw_image: {e}")
            import traceback
            traceback.print_exc()
            return -1
    
    def _save_raw(self, file_path):
        """RAW 이미지 저장"""
        try:
            # 파일 경로 확장자 확인
            if not file_path.lower().endswith('.raw'):
                file_path = file_path.rsplit('.', 1)[0] + '.raw'
            
            # HB 포맷인 경우 디코딩 필요
            if self.st_frame_info.enPixelType in HB_format_list:
                # 디코딩 파라미터
                stDecodeParam = MV_CC_HB_DECODE_PARAM()
                memset(byref(stDecodeParam), 0, sizeof(stDecodeParam))
                
                # PayloadSize 가져오기
                stParam = MVCC_INTVALUE()
                memset(byref(stParam), 0, sizeof(stParam))
                
                ret = self.obj_cam.MV_CC_GetIntValue("PayloadSize", stParam)
                if ret != 0:
                    print(f"Camera {self.camera_id}: Get PayloadSize fail! ret[0x{ret:x}]")
                    return ret
                
                nPayloadSize = stParam.nCurValue
                stDecodeParam.pSrcBuf = cast(self.buf_save_image, POINTER(c_ubyte))
                stDecodeParam.nSrcLen = self.st_frame_info.nFrameLen
                stDecodeParam.pDstBuf = (c_ubyte * nPayloadSize)()
                stDecodeParam.nDstBufSize = nPayloadSize
                
                ret = self.obj_cam.MV_CC_HBDecode(stDecodeParam)
                if ret != 0:
                    print(f"Camera {self.camera_id}: HB Decode fail! ret[0x{ret:x}]")
                    return ret
                
                # 디코딩된 데이터를 파일로 저장
                try:
                    with open(file_path, 'wb') as file_open:
                        img_save = (c_ubyte * stDecodeParam.nDstBufLen)()
                        cdll.msvcrt.memmove(byref(img_save), stDecodeParam.pDstBuf, stDecodeParam.nDstBufLen)
                        file_open.write(img_save)
                    print(f"Camera {self.camera_id}: RAW image (HB decoded) saved to {file_path}")
                    return 0
                except PermissionError:
                    print(f"Camera {self.camera_id}: Permission error saving RAW file: {file_path}")
                    return MV_E_OPENFILE
            else:
                # 일반 RAW 포맷 - 직접 저장
                try:
                    with open(file_path, 'wb') as file_open:
                        img_save = (c_ubyte * self.st_frame_info.nFrameLen)()
                        cdll.msvcrt.memmove(byref(img_save), cast(self.buf_save_image, POINTER(c_ubyte)), self.st_frame_info.nFrameLen)
                        file_open.write(img_save)
                    print(f"Camera {self.camera_id}: RAW image saved to {file_path}")
                    return 0
                except PermissionError:
                    print(f"Camera {self.camera_id}: Permission error saving RAW file: {file_path}")
                    return MV_E_OPENFILE
                    
        except Exception as e:
            print(f"Camera {self.camera_id}: Error in _save_raw: {e}")
            import traceback
            traceback.print_exc()
            return -1


class CameraManager:
    """제조사 예제 방식의 카메라 관리자 (비동기 지원)"""
    
    def __init__(self):
        self.camera_operations = [None] * 4  # 각 카메라별 CameraOperation 인스턴스
        self.device_list = None
        self.is_initialized = False
        self.camera_ip_mapping = {}  # backend slot (0-3) -> DB IP
    
    def _get_error_message(self, error_code):
        """에러 코드에 따른 메시지 반환"""
        error_messages = {
            0x8000000D: "No Available Buffer - No output buffer available",
            0x80000203: "Access Denied - Device may be already opened by another process",
            0x80000204: "Device Busy - Device is busy or network disconnected",
            0x80000205: "Network Packet Error",
            0x80000206: "Network Error",
        }
        return error_messages.get(error_code, f"Unknown error (0x{error_code:x})")
    
    def _get_gige_ip(self, mvcc_dev_info):
        """GigE 카메라의 IP 주소 추출"""
        try:
            nip1 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
            nip2 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
            nip3 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
            nip4 = (mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
            return f"{nip1}.{nip2}.{nip3}.{nip4}"
        except:
            return None
    
    def _parse_device_list(self, deviceList):
        """deviceList에서 디바이스 정보 추출 (공통 로직)"""
        devices = []
        for i in range(deviceList.nDeviceNum):
            try:
                mvcc_dev_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                strModeName = ""
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chModelName:
                    if per == 0:
                        break
                    strModeName = strModeName + chr(per)
                ip_address = self._get_gige_ip(mvcc_dev_info)
                serial_number = ""
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chSerialNumber:
                    if per == 0:
                        break
                    serial_number = serial_number + chr(per)
                user_name = ""
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chUserDefinedName:
                    if per == 0:
                        break
                    user_name = user_name + chr(per)
                device_info = {
                    "device_index": i,
                    "model_name": strModeName,
                    "ip_address": ip_address if ip_address else "N/A",
                    "serial_number": serial_number if serial_number else "N/A",
                    "user_name": user_name if user_name else "N/A",
                    "device_type": "GigE"
                }
                devices.append(device_info)
            except Exception as e:
                print(f"Error processing device {i}: {e}")
                continue
        return devices

    async def get_device_list(self):
        """디바이스 리스트 조회.
        카메라가 이미 초기화/스트리밍 중이면 MV_CC_Finalize를 호출하지 않음 (스트리밍 유지).
        """
        try:
            deviceList = MV_CC_DEVICE_INFO_LIST()
            tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE

            if self.is_initialized:
                # 이미 SDK 사용 중: EnumDevices만 호출, Finalize 호출 금지 (스트리밍 유지)
                ret = await asyncio.to_thread(MvCamera.MV_CC_EnumDevices, tlayerType, deviceList)
                if ret != 0:
                    print(f"Enum devices fail! ret[0x{ret:x}]")
                    return None
                if deviceList.nDeviceNum == 0:
                    return []
                return self._parse_device_list(deviceList)

            # SDK 미초기화: Init → EnumDevices → Finalize
            ret = await asyncio.to_thread(MvCamera.MV_CC_Initialize)
            if ret != 0:
                print(f"SDK Initialize fail! ret[0x{ret:x}]")
                return None
            
            ret = await asyncio.to_thread(MvCamera.MV_CC_EnumDevices, tlayerType, deviceList)
            if ret != 0:
                print(f"Enum devices fail! ret[0x{ret:x}]")
                try:
                    await asyncio.to_thread(MvCamera.MV_CC_Finalize)
                except:
                    pass
                return None
            
            if deviceList.nDeviceNum == 0:
                try:
                    await asyncio.to_thread(MvCamera.MV_CC_Finalize)
                except:
                    pass
                return []
            
            devices = self._parse_device_list(deviceList)
            try:
                await asyncio.to_thread(MvCamera.MV_CC_Finalize)
            except:
                pass
            return devices
            
        except Exception as e:
            print(f"Error getting device list: {str(e)}")
            import traceback
            traceback.print_exc()
            if not self.is_initialized:
                try:
                    await asyncio.to_thread(MvCamera.MV_CC_Finalize)
                except:
                    pass
            return None
    
    async def initialize(self):
        """카메라 초기화 (제조사 예제 방식)"""
        try:
            # 기존 카메라 정리
            await self.cleanup()
            
            # SDK 초기화
            ret = await asyncio.to_thread(MvCamera.MV_CC_Initialize)
            if ret != 0:
                print(f"SDK Initialize fail! ret[0x{ret:x}]")
                return False
            
            # 디바이스 열거
            deviceList = MV_CC_DEVICE_INFO_LIST()
            tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE
            ret = await asyncio.to_thread(MvCamera.MV_CC_EnumDevices, tlayerType, deviceList)
            if ret != 0:
                print(f"Enum devices fail! ret[0x{ret:x}]")
                return False
            
            if deviceList.nDeviceNum == 0:
                print("No device found!")
                return False
            
            print(f"Found {deviceList.nDeviceNum} devices!")
            self.device_list = deviceList
            
            # DB에서 카메라 IP 매핑 정보 가져오기
            camera_ip_mapping = {}
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get("http://localhost:8000/camera/get_feature")
                    if response.status_code == 200:
                        camera_features = response.json()
                        for feature in camera_features:
                            camera_number = feature.get('CAMERA')
                            ip_address = feature.get('IP')
                            if camera_number and ip_address:
                                camera_id = camera_number - 1
                                camera_ip_mapping[camera_id] = ip_address
                                print(f"DB Mapping: Camera {camera_id} (UI: {camera_number}) -> IP: {ip_address}")
            except Exception as e:
                print(f"Error fetching camera IP mapping from DB: {e}")
            self.camera_ip_mapping = dict(camera_ip_mapping)
            
            # 디바이스 리스트와 IP 정보 수집
            device_info_list = []
            for i in range(deviceList.nDeviceNum):
                mvcc_dev_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                ip_address = self._get_gige_ip(mvcc_dev_info)
                device_info_list.append({
                    'device_index': i,
                    'device_info': mvcc_dev_info,
                    'ip_address': ip_address
                })
            
            # IP 매핑 기반으로 카메라 초기화
            camera_to_device_mapping = {}
            used_device_indices = set()
            
            # 1. DB에 IP가 있는 카메라부터 매핑
            for camera_id in range(4):
                if camera_id in camera_ip_mapping:
                    target_ip = camera_ip_mapping[camera_id]
                    for device_info in device_info_list:
                        if (device_info['device_index'] not in used_device_indices and
                            device_info['ip_address'] == target_ip):
                            camera_to_device_mapping[camera_id] = device_info['device_index']
                            used_device_indices.add(device_info['device_index'])
                            print(f"Mapped Camera {camera_id} to device index {device_info['device_index']} (IP: {target_ip})")
                            break
            
            # 2. IP가 없는 카메라는 인덱스 순서대로 매핑
            device_index = 0
            for camera_id in range(4):
                if camera_id not in camera_to_device_mapping:
                    while device_index < len(device_info_list):
                        if device_info_list[device_index]['device_index'] not in used_device_indices:
                            camera_to_device_mapping[camera_id] = device_info_list[device_index]['device_index']
                            used_device_indices.add(device_info_list[device_index]['device_index'])
                            print(f"Auto-mapped Camera {camera_id} to device index {device_info_list[device_index]['device_index']} (IP: {device_info_list[device_index]['ip_address']})")
                            device_index += 1
                            break
                        device_index += 1
                    if device_index >= len(device_info_list):
                        break
            
            # 각 카메라 초기화 (순차적으로)
            initialized_count = 0
            for camera_id in range(4):
                if camera_id not in camera_to_device_mapping:
                    db_ip = camera_ip_mapping.get(camera_id, "N/A")
                    print(
                        f"Camera {camera_id} (UI: {camera_id + 1}) has no device mapping"
                        f" (DB IP: {db_ip}), skipping..."
                    )
                    continue
                
                device_index = camera_to_device_mapping[camera_id]
                stDeviceList = cast(deviceList.pDeviceInfo[device_index], POINTER(MV_CC_DEVICE_INFO)).contents
                
                # CameraOperation 인스턴스 생성
                cam_operation = CameraOperation(n_connect_num=camera_id)
                ret = await asyncio.to_thread(cam_operation.open_device, stDeviceList)
                
                if ret == 0 and cam_operation.b_open_device:
                    self.camera_operations[camera_id] = cam_operation
                    initialized_count += 1
                    print(f"Camera {camera_id} (UI: {camera_id + 1}) initialized successfully")
                else:
                    err = ret if ret != 0 else 0x80000203
                    print(
                        f"Camera {camera_id} (UI: {camera_id + 1}) initialization failed: "
                        f"{self._get_error_message(err)} (ret[0x{err:x}])"
                    )
                    self.camera_operations[camera_id] = None
                
                # 카메라 간 초기화 지연
                await asyncio.sleep(0.2)
            
            if initialized_count == 0:
                print("No cameras initialized successfully")
                return False
            
            self.is_initialized = True
            print(f"Total {initialized_count} camera(s) initialized successfully")
            return True
            
        except Exception as e:
            print(f"Error initializing cameras: {str(e)}")
            return False

    async def initialize_with_retry(self, max_attempts=5, retry_delay=2.0):
        """Access Denied 등 일시 오류 시 카메라 초기화 재시도"""
        for attempt in range(max_attempts):
            if await self.initialize():
                return True
            if attempt < max_attempts - 1:
                print(
                    f"Camera initialization attempt {attempt + 1}/{max_attempts} failed, "
                    f"retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)
        return False
    
    async def set_feature(self, camera_id, fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format):
        """카메라 설정 변경 (비동기)"""
        if camera_id < 0 or camera_id >= 4:
            return None
        
        if self.camera_operations[camera_id] is None:
            return None
        
        try:
            result = await asyncio.to_thread(
                self.camera_operations[camera_id].set_feature,
                fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format
            )
            return result
        except Exception as e:
            print(f"Error setting features for camera {camera_id}: {e}")
            return None
    
    async def get_feature(self, camera_id):
        """카메라 설정 조회 (비동기)"""
        if camera_id < 0 or camera_id >= 4:
            print(f"Invalid camera_id: {camera_id}")
            return None
        
        if self.camera_operations[camera_id] is None:
            print(f"Camera {camera_id} is not initialized")
            return None
        
        try:
            settings = await asyncio.to_thread(self.camera_operations[camera_id].get_feature)
            if settings is None:
                print(f"Camera {camera_id}: get_feature returned None (device may not be open)")
            return settings
        except Exception as e:
            print(f"Error getting features for camera {camera_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_status(self, camera_id=None):
        """카메라 상태 조회"""
        try:
            if camera_id is not None:
                if camera_id < 0 or camera_id >= 4:
                    return None
                cam_op = self.camera_operations[camera_id]
                is_open = cam_op is not None and cam_op.b_open_device if cam_op else False
                is_grabbing = cam_op is not None and cam_op.b_start_grabbing if cam_op else False
                return {
                    "camera_id": camera_id,
                    "ui_camera_id": camera_id + 1,
                    "device_ip": cam_op.device_ip if cam_op else None,
                    "db_ip": self.camera_ip_mapping.get(camera_id),
                    "is_open": is_open,
                    "is_grabbing": is_grabbing,
                    "is_running": is_grabbing,  # WebSocket 엔드포인트 호환성
                    "has_camera": cam_op is not None  # WebSocket 엔드포인트 호환성
                }
            else:
                status_list = []
                for i in range(4):
                    cam_op = self.camera_operations[i]
                    is_open = cam_op is not None and cam_op.b_open_device if cam_op else False
                    is_grabbing = cam_op is not None and cam_op.b_start_grabbing if cam_op else False
                    status_list.append({
                        "camera_id": i,
                        "ui_camera_id": i + 1,
                        "device_ip": cam_op.device_ip if cam_op else None,
                        "db_ip": self.camera_ip_mapping.get(i),
                        "is_open": is_open,
                        "is_grabbing": is_grabbing,
                        "is_running": is_grabbing,
                        "has_camera": cam_op is not None
                    })
                return {
                    "is_initialized": self.is_initialized,
                    "cameras": status_list
                }
        except Exception as e:
            print(f"Error getting camera status: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_frame(self, camera_id: int, stream_width=1280, stream_height=720):
        """
        특정 카메라의 프레임을 JPEG로 가져오기 (스트리밍용 해상도 축소)
        
        Args:
            camera_id: 카메라 ID (0-3)
            stream_width: 스트리밍용 너비 (기본값: 1280)
            stream_height: 스트리밍용 높이 (기본값: 720)
        
        Returns:
            bytes: JPEG 이미지 데이터 (축소된 해상도)
        """
        if camera_id < 0 or camera_id >= 4:
            return None
        
        if self.camera_operations[camera_id] is None:
            return None
        
        cam_op = self.camera_operations[camera_id]
        
        # 카메라가 그래빙 중인지 확인
        if not cam_op.b_start_grabbing:
            return None
        
        # 저장 중이면 None 반환 (스트리밍 일시 중지)
        if cam_op.b_saving:
            return None
        
        try:
            # CameraOperation의 get_frame_jpeg 메서드 사용 (해상도 파라미터 전달)
            jpeg_data = await asyncio.to_thread(cam_op.get_frame_jpeg, stream_width, stream_height)
            return jpeg_data
        except Exception as e:
            print(f"Error getting frame for camera {camera_id}: {e}")
            return None
    
    async def stop_grabbing(self):
        """모든 카메라 그래빙 중지 (제조사 예제 방식)"""
        try:
            for i in range(0, 4):
                if self.camera_operations[i] is not None:
                    ret = await asyncio.to_thread(self.camera_operations[i].stop_grabbing)
                    if 0 != ret:
                        print(f"Camera {i} stop grabbing fail! ret = {self._to_hex_str(ret)}")
            
            print("All cameras stopped grabbing")
            return True
        except Exception as e:
            print(f"Error stopping grabbing: {str(e)}")
            return False

    async def restart(self):
        """카메라 시스템 재시작"""
        try:
            await self.stop_grabbing()
            await self.cleanup()
            await asyncio.sleep(2.0)
            return await self.start_grabbing()
        except Exception as e:
            print(f"Error restarting camera system: {e}")
            return False

    async def cleanup(self):
        """모든 카메라 정리"""
        try:
            for camera_id in range(4):
                if self.camera_operations[camera_id] is not None:
                    ret = await asyncio.to_thread(self.camera_operations[camera_id].close_device)
                    if ret != 0:
                        print(f"Camera {camera_id}: Close device fail! ret[0x{ret:x}]")
                    self.camera_operations[camera_id] = None
            
            # SDK 정리
            try:
                await asyncio.to_thread(MvCamera.MV_CC_Finalize)
            except:
                pass
            
            self.is_initialized = False
            print("All cameras cleaned up")
            return True
            
        except Exception as e:
            print(f"Error cleaning up cameras: {str(e)}")
            return False

    async def start_grabbing(self):
        """모든 카메라 그래빙 시작 (제조사 예제 방식)"""
        if not self.is_initialized:
            if not await self.initialize_with_retry():
                return False
        
        try:
            for i in range(0, 4):
                if self.camera_operations[i] is not None:
                    # 제조사 예제: start_grabbing(n_index, win_handle)
                    # win_handle은 None으로 처리 (WebSocket 사용하므로)
                    ret = await asyncio.to_thread(self.camera_operations[i].start_grabbing, i, None)
                    if 0 != ret:
                        print(f"Camera {i} start grabbing fail! ret = {self._to_hex_str(ret)}")
            
            print("All cameras started grabbing")
            return True
        except Exception as e:
            print(f"Error starting grabbing: {str(e)}")
            return False
    
    def _to_hex_str(self, num):
        """에러 코드를 16진수 문자열로 변환"""
        chaDic = {10: 'a', 11: 'b', 12: 'c', 13: 'd', 14: 'e', 15: 'f'}
        hexStr = ""
        if num < 0:
            num = num + 2**32
        while num >= 16:
            digit = num % 16
            hexStr = chaDic.get(digit, str(digit)) + hexStr
            num //= 16
        hexStr = chaDic.get(num, str(num)) + hexStr
        return hexStr


# 전역 인스턴스 생성
camera_manager = CameraManager()

# 카메라별 마지막 저장 이미지 경로 캐시 (camera_id 0-3 -> f0000 전체 경로)
last_saved_paths: dict = {}


def _sync_turn_off_light_channels_after_save() -> None:
    """
    저장 완료 후 RS-232로 채널 1·2 밝기 0 전송.
    LIGHT_OFF_AFTER_SAVE=0 이면 save_image 쪽에서 호출하지 않음.
    주의: 한 트리거에 여러 카메라가 겹쳐 같은 조명을 쓰면, 먼저 끝난 카메라가 조명을 꺼
    나머지 촬영에 영향을 줄 수 있음.
    """
    try:
        from utils.light_serial import send_light_rs232

        for ch in (1, 2):
            try:
                send_light_rs232(ch, 0)
            except Exception as e:
                logger.warning("저장 후 조명 끄기 실패 ch=%s: %s", ch, e)
    except Exception as e:
        logger.warning("저장 후 조명 끄기: %s", e)


def get_last_saved_path(camera_id: int) -> str | None:
    """
    카메라별 마지막 저장된 이미지 경로(f0000) 반환.
    camera_id: UI 기준 1-4 (내부적으로 0-3으로 변환)
    """
    if camera_id < 1 or camera_id > 4:
        return None
    return last_saved_paths.get(camera_id - 1)


# 전역 함수들 (래퍼 함수)
async def set_feature(camera_id: int, fpsenable: int, fps: float, gainauto: int, gain: float, exposuretime: float, width: int, height: int, pixel_format: int):
    return await camera_manager.set_feature(camera_id, fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format)

async def get_feature(camera_id: int):
    return await camera_manager.get_feature(camera_id)

async def get_camera_status(camera_id: int = None):
    return await camera_manager.get_status(camera_id)

async def get_device_list():
    return await camera_manager.get_device_list()

async def start_grabbing():
    return await camera_manager.start_grabbing()

async def stop_grabbing():
    return await camera_manager.stop_grabbing()

async def get_frame(camera_id: int, stream_width=1280, stream_height=720):
    """
    특정 카메라의 프레임을 JPEG로 가져오기 (스트리밍용 해상도 축소)
    
    Args:
        camera_id: 카메라 ID (0-3)
        stream_width: 스트리밍용 너비 (기본값: 1280)
        stream_height: 스트리밍용 높이 (기본값: 720)
    
    Returns:
        bytes: JPEG 이미지 데이터 (축소된 해상도)
    """
    return await camera_manager.get_frame(camera_id, stream_width, stream_height)

async def get_frame_save(camera_id: int, save_path=None):
    """프레임 가져오기 및 저장"""
    frame_data = await camera_manager.get_frame(camera_id)
    if frame_data and save_path:
        daystamp = time.strftime("%Y%m%d")
        save_dir = os.path.join(save_path, daystamp)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(save_dir, f'image_{timestamp}.jpg')
        with open(file_path, 'wb') as f:
            f.write(frame_data)
    return frame_data

async def save_image(camera_id: int, save_path: str, save_type: int = 2, quality: int = 99, file_name: str = None, frame_count: int = 1):
    """
    특정 카메라의 이미지를 원본 사이즈로 저장 (단일 또는 연속 프레임)
    저장 중에는 스트리밍이 일시 중지됩니다.
    
    Args:
        camera_id: 카메라 ID (0-3)
        save_path: 저장할 디렉토리 경로
        save_type: 저장 타입 (1=JPG, 2=BMP, 3=TIF, 4=PNG, 0=RAW)
        quality: JPG 품질 (50-99, 다른 포맷에서는 무시)
        file_name: 파일명 (None이면 자동 생성, frame_count > 1일 때는 무시)
        frame_count: 저장할 프레임 개수 (기본값: 1)
    
    Returns:
        dict: {"success": bool, "file_paths": list, "error": str}
    """
    if camera_id < 0 or camera_id >= 4:
        return {"success": False, "file_paths": [], "error": f"Invalid camera_id: {camera_id}"}
    
    if camera_manager.camera_operations[camera_id] is None:
        return {"success": False, "file_paths": [], "error": f"Camera {camera_id} is not initialized"}
    
    cam_op = camera_manager.camera_operations[camera_id]
    
    # 카메라가 그래빙 중인지 확인
    if not cam_op.b_start_grabbing:
        return {"success": False, "file_paths": [], "error": f"Camera {camera_id} is not grabbing"}
    
    try:
        # 디렉토리 생성
        os.makedirs(save_path, exist_ok=True)
        
        saved_files = []
        base_timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # 저장 시작 플래그 설정 (스트리밍 일시 중지)
        # 주의: cam_op.save_image() 내부에서도 플래그를 설정하지만,
        # 연속 프레임 저장 시 전체 저장 과정 동안 유지하기 위해 여기서도 설정
        cam_op.b_saving = True
        
        try:
            # 연속 프레임 저장 (최적화: 대기 시간 단축)
            # 주의: 카메라 버퍼는 하나이므로 순차적으로 읽어야 함
            # 각 프레임마다 버퍼가 업데이트되므로 병렬 저장은 불가능
            # 하지만 대기 시간을 최소화하여 전체 저장 시간 단축 가능
            
            for frame_idx in range(frame_count):
                # 각 프레임마다 버퍼 확인 (최신 프레임 가져오기)
                if not cam_op.buf_save_image:
                    logger.warning(f"Camera {camera_id}: No image buffer available for frame {frame_idx + 1}/{frame_count}")
                    await asyncio.sleep(0.01)  # 짧은 대기 (10ms로 단축)
                    continue
                
                # 파일명 생성: Cam1~4 (camera_id 0~3 -> Cam1~4)
                cam_display_id = camera_id + 1
                if frame_count > 1:
                    if save_type == 1:
                        file_name = f"Cam{cam_display_id}_{base_timestamp}_f{frame_idx:04d}.jpg"
                    elif save_type == 2:
                        file_name = f"Cam{cam_display_id}_{base_timestamp}_f{frame_idx:04d}.bmp"
                    elif save_type == 3:
                        file_name = f"Cam{cam_display_id}_{base_timestamp}_f{frame_idx:04d}.tif"
                    elif save_type == 4:
                        file_name = f"Cam{cam_display_id}_{base_timestamp}_f{frame_idx:04d}.png"
                    else:  # save_type == 0
                        file_name = f"Cam{cam_display_id}_{base_timestamp}_f{frame_idx:04d}.raw"
                else:
                    # 단일 프레임인 경우 기존 로직 사용
                    if file_name is None:
                        frame_num = cam_op.st_frame_info.nFrameNum if hasattr(cam_op.st_frame_info, 'nFrameNum') else 0
                        if save_type == 1:
                            file_name = f"Cam{cam_display_id}_{base_timestamp}_fn{frame_num}.jpg"
                        elif save_type == 2:
                            file_name = f"Cam{cam_display_id}_{base_timestamp}_fn{frame_num}.bmp"
                        elif save_type == 3:
                            file_name = f"Cam{cam_display_id}_{base_timestamp}_fn{frame_num}.tif"
                        elif save_type == 4:
                            file_name = f"Cam{cam_display_id}_{base_timestamp}_fn{frame_num}.png"
                        else:  # save_type == 0
                            file_name = f"Cam{cam_display_id}_{base_timestamp}_fn{frame_num}.raw"
                
                # 전체 파일 경로 생성
                full_path = os.path.join(save_path, file_name)
                
                # 이미지 저장 (동기 함수를 비동기로 실행)
                # 버퍼에서 읽고 파일로 저장하는 작업은 순차적으로 처리해야 함
                ret = await asyncio.to_thread(cam_op.save_image, full_path, save_type, quality)
                
                if ret == 0:
                    saved_files.append(full_path)
                    # 로그는 간소화 (너무 많은 로그는 성능 저하)
                    if frame_idx % 5 == 0 or frame_idx == frame_count - 1:  # 5프레임마다 또는 마지막 프레임만 로그
                        logger.info(f"Camera {camera_id}: Saved frame {frame_idx + 1}/{frame_count} to {full_path}")
                else:
                    logger.error(f"Camera {camera_id}: Failed to save frame {frame_idx + 1}: ret[0x{ret:x}]")
                
                # 다음 프레임을 위해 최소 대기 (버퍼 업데이트 대기)
                # 프레임 레이트에 따라 조정: 30fps면 약 33ms, 60fps면 약 16ms
                # 카메라가 빠르게 업데이트할 수 있으므로 10ms로 단축 (기존 50ms에서 5배 개선)
                if frame_idx < frame_count - 1:
                    await asyncio.sleep(0.01)  # 10ms 대기 (기존 50ms에서 5배 개선)
        finally:
            # 저장 완료 플래그 해제 (스트리밍 재개)
            cam_op.b_saving = False
        
        if saved_files:
            # f0000 경로 캐시 (카메라별 개별 저장)
            last_saved_paths[camera_id] = saved_files[0]
            # 캐시 반영 직후 조명 끄기 (기본 ON, LIGHT_OFF_AFTER_SAVE=0/false/no/off 로 비활성화)
            if os.environ.get("LIGHT_OFF_AFTER_SAVE", "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            ):
                await asyncio.to_thread(_sync_turn_off_light_channels_after_save)
            return {
                "success": True,
                "file_paths": saved_files,
                "file_path": saved_files[0] if len(saved_files) == 1 else None,  # 단일 프레임 호환성
                "error": None
            }
        else:
            return {
                "success": False,
                "file_paths": [],
                "file_path": None,
                "error": f"Failed to save any frames for camera {camera_id}"
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 에러 발생 시에도 플래그 해제
        if camera_manager.camera_operations[camera_id] is not None:
            camera_manager.camera_operations[camera_id].b_saving = False
        return {
            "success": False,
            "file_paths": [],
            "file_path": None,
            "error": f"Exception: {str(e)}"
        }


# 기존 코드와의 호환성
cameragrab = camera_manager
