import os
import sys
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

from threading import *
from ctypes import *
from ctypes import cdll
from utils.MvCameraControl_class import *
from utils.CamOperation_class import *
from utils.MvCameraControl_class import *
from utils.MvErrorDefine_const import *
from utils.CameraParams_header import *
import numpy as np
import cv2
import asyncio
import time
import httpx

def save_non_raw_image(save_type, frame_info, cam_instance,save_path,frame_number):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    if save_type == 1:
        mv_image_type = MV_Image_Jpeg
        file_path = save_path + f"Image_w{frame_info.stFrameInfo.nWidth}_h{frame_info.stFrameInfo.nHeight}_{timestamp}_frame{frame_number}.jpg"
    elif save_type == 2:
        mv_image_type = MV_Image_Bmp
        file_path = save_path + f"Image_w{frame_info.stFrameInfo.nWidth}_h{frame_info.stFrameInfo.nHeight}_{timestamp}_frame{frame_number}.bmp"
    elif save_type == 3:
        mv_image_type = MV_Image_Tif
        file_path = save_path + f"Image_w{frame_info.stFrameInfo.nWidth}_h{frame_info.stFrameInfo.nHeight}_{timestamp}_frame{frame_number}.tif"
    else:
        mv_image_type = MV_Image_Png            
        file_path = save_path + f"Image_w{frame_info.stFrameInfo.nWidth}_h{frame_info.stFrameInfo.nHeight}_{timestamp}_frame{frame_number}.png"

    c_file_path = file_path.encode('ascii')
    stSaveParam = MV_SAVE_IMAGE_TO_FILE_PARAM_EX()
    stSaveParam.enPixelType = frame_info.stFrameInfo.enPixelType  # ch:카메라对应的像素格式 | en:Camera pixel type
    stSaveParam.nWidth = frame_info.stFrameInfo.nWidth  # ch:카메라对应的宽 | en:Width
    stSaveParam.nHeight = frame_info.stFrameInfo.nHeight  # ch:카메라对应的高 | en:Height
    stSaveParam.nDataLen = frame_info.stFrameInfo.nFrameLen
    stSaveParam.pData = frame_info.pBufAddr
    stSaveParam.enImageType = mv_image_type  # ch:需要保存的图像类型 | en:Image format to save
    stSaveParam.pcImagePath = create_string_buffer(c_file_path)
    stSaveParam.iMethodValue = 1
    stSaveParam.nQuality = 99  # ch: JPG: (50,99], invalid in other format
    
    # 디버깅 정보 출력
    #print(f"Saving image to: {file_path}")
    #print(f"PixelType: {stSaveParam.enPixelType}")
    #print(f"Width: {stSaveParam.nWidth}")
    #print(f"Height: {stSaveParam.nHeight}")
    #print(f"DataLen: {stSaveParam.nDataLen}")
    #print(f"pData: {stSaveParam.pData}")

    mv_ret = cam_instance.MV_CC_SaveImageToFileEx(stSaveParam)
    return mv_ret

def take_frame_from_buffer(frame_info, buf_save_image, cam_instance):
    """복사된 버퍼에서 SDK 함수를 사용하여 RGB 변환 (제조사 예제 방식 개선)"""
    try:
        height = frame_info.nHeight
        width = frame_info.nWidth
        
        # RGB 변환을 위한 버퍼 크기 계산
        nDataSize = width * height * 3
        pData = (c_ubyte * nDataSize)()
        
        # 복사된 버퍼를 사용하여 프레임 정보 구조체 생성
        temp_frame_info = MV_FRAME_OUT_INFO_EX()
        cdll.msvcrt.memcpy(byref(temp_frame_info), byref(frame_info), sizeof(MV_FRAME_OUT_INFO_EX))
        
        # 복사된 버퍼를 pBufAddr로 설정 (SDK가 사용할 수 있도록)
        temp_frame_info.pBufAddr = cast(buf_save_image, POINTER(c_ubyte))
        
        # SDK 함수를 사용하여 RGB 변환 (복사된 버퍼 사용)
        ret = cam_instance.MV_CC_GetImageForRGB(pData, nDataSize, temp_frame_info, 1000)
        if ret == 0:
            img_array = np.frombuffer(pData, dtype=np.uint8)
            img = img_array.reshape((height, width, 3))
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return buffer
        else:
            print(f"Failed to convert image: ret[0x{ret:x}]")
            return None
        
    except Exception as e:
        print(f"Error in take_frame_from_buffer: {e}")
        return None

def take_frame(frame_info, cam_instance):
    """기존 함수 (하위 호환성 유지, 사용하지 않음)"""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        nDataSize = frame_info.stFrameInfo.nWidth * frame_info.stFrameInfo.nHeight * 3
        pData = (c_ubyte * nDataSize)()
        ret = cam_instance.MV_CC_GetImageForRGB(pData, nDataSize, frame_info.stFrameInfo, 1000)
        if ret == 0:
            img_array = np.frombuffer(pData, dtype=np.uint8)
            img = img_array.reshape((frame_info.stFrameInfo.nHeight, frame_info.stFrameInfo.nWidth, 3))
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return buffer
        else:
            print(f"Failed to get image: ret[0x{ret:x}]")
            return None

    except Exception as e:
        print(f"Error in get_frame: {e}")
        return None

def take_frame_save(frame_info, cam_instance, save_path=None):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    daystamp = time.strftime("%Y%m%d")
    
    # save_path가 전달되지 않으면 기본 경로 사용
    if save_path is None:
        save_path = "D:onclick/stream/" + daystamp + "/"
    else:
        # 전달된 경로에 날짜 폴더 추가
        save_path = os.path.join(save_path, daystamp) + "/"
    
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    try:
        nDataSize = frame_info.stFrameInfo.nWidth * frame_info.stFrameInfo.nHeight * 3
        pData = (c_ubyte * nDataSize)()
        ret = cam_instance.MV_CC_GetImageForRGB(pData, nDataSize, frame_info.stFrameInfo, 1000)
        if ret == 0:
            img_array = np.frombuffer(pData, dtype=np.uint8)
            img = img_array.reshape((frame_info.stFrameInfo.nHeight, frame_info.stFrameInfo.nWidth, 3))
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            cv2.imwrite(save_path + 'image_%s.jpg' % timestamp, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return buffer
        else:
            print(f"Failed to get image: ret[0x{ret:x}]")
            return None

    except Exception as e:
        print(f"Error in get_frame: {e}")
        return None

def set_camera_settings(cam_instance, fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format):
    try:        
        pixel_format_map = {
            1: 17301505,  # PixelType_Gvsp_Mono8
            2: 17825795,  # PixelType_Gvsp_Mono10
            3: 17825797,  # PixelType_Gvsp_Mono12
            4: 35127316,  # PixelType_Gvsp_RGB8_Packed
            5: 35127317,  # PixelType_Gvsp_BGR8_Packed
            6: 34603058,  # PixelType_Gvsp_YUV422_YUYV_Packed
            7: 34603039,  # PixelType_Gvsp_YUV422_Packed
            8: 17301513,  # PixelType_Gvsp_BayerRG8
            9: 17825805,  # PixelType_Gvsp_BayerRG10
            10: 17563687, # PixelType_Gvsp_BayerRG10_Packed
            11: 17825809, # PixelType_Gvsp_BayerRG12
            12: 17563691  # PixelType_Gvsp_BayerRG12_Packed
        }  
        ret = cam_instance.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", fpsenable) # 0: disable, 1: enable   
        if fpsenable == 1:
            ret = cam_instance.MV_CC_SetFloatValue("AcquisitionFrameRate", fps)

        ret = cam_instance.MV_CC_SetEnumValue("GainAuto", gainauto)  # 0: Off, 1: Once, 2: Continuous
        if gainauto == 0:
            ret = cam_instance.MV_CC_SetFloatValue("Gain", gain)

        ret = cam_instance.MV_CC_SetFloatValue("ExposureTime", exposuretime)         
        ret = cam_instance.MV_CC_SetIntValue("Width", width)
        ret = cam_instance.MV_CC_SetIntValue("Height", height)          
        ret = cam_instance.MV_CC_SetEnumValue("PixelFormat", pixel_format_map[pixel_format])
        return True

    except Exception as e:
        print(f"Error setting camera settings: {e}")
        return None

def get_camera_settings(cam_instance):   
    settings = {}    
    try:
        stParam = MVCC_INTVALUE()
        ret = cam_instance.MV_CC_GetBoolValue("AcquisitionFrameRateEnable", stParam)
        if ret == 0:
            settings['AcquisitionFrameRateEnable'] = stParam.nCurValue

        stParam = MVCC_FLOATVALUE()
        ret = cam_instance.MV_CC_GetFloatValue("AcquisitionFrameRate", stParam)
        if ret == 0:
            settings['AcquisitionFrameRate'] = stParam.fCurValue

        stParam = MVCC_FLOATVALUE()
        ret = cam_instance.MV_CC_GetFloatValue("ResultingFrameRate", stParam)
        if ret == 0:
            settings['ResultingFrameRate'] = stParam.fCurValue

        stParam = MVCC_ENUMVALUE()
        ret = cam_instance.MV_CC_GetEnumValue("GainAuto", stParam)
        if ret == 0:
            settings['GainAuto'] = stParam.nCurValue

        stParam = MVCC_FLOATVALUE()
        ret = cam_instance.MV_CC_GetFloatValue("Gain", stParam)
        if ret == 0:
            settings['Gain'] = stParam.fCurValue

        stParam = MVCC_FLOATVALUE()
        ret = cam_instance.MV_CC_GetFloatValue("ExposureTime", stParam)
        if ret == 0:
            settings['ExposureTime'] = stParam.fCurValue

        stParam = MVCC_INTVALUE()
        ret = cam_instance.MV_CC_GetIntValue("Width", stParam)
        if ret == 0:
            settings['Width'] = stParam.nCurValue

        stParam = MVCC_INTVALUE()
        ret = cam_instance.MV_CC_GetIntValue("Height", stParam)
        if ret == 0:
            settings['Height'] = stParam.nCurValue
        
        stParam = MVCC_ENUMVALUE()
        ret = cam_instance.MV_CC_GetEnumValue("PixelFormat", stParam)
        if ret == 0:
            settings['PixelFormat'] = stParam.nCurValue

        stParam = MVCC_ENUMVALUE()
        ret = cam_instance.MV_CC_GetEnumValue("TestPattern", stParam)
        if ret == 0:
            settings['TestPattern'] = stParam.nCurValue

        return settings

    except Exception as e:
        print(f"Error getting camera settings: {e}")
        return None

class CameraGrab:
    def __init__(self):
        self.cams = [None] * 4  # 4개 카메라 인스턴스
        self.stOutFrames = [None] * 4  # 4개 카메라 프레임 버퍼
        self.is_running = False  # 카메라 실행 상태 추가
        self.is_capturing = [False] * 4  # 각 카메라별 캡처 상태 플래그
        self.frame_buffer = []
        self.grab_tasks = [None] * 4  # 각 카메라별 grab 태스크
        self.frame_locks = [asyncio.Lock() for _ in range(4)]  # 각 카메라별 프레임 접근 락
        self.frame_cache = [None] * 4  # 각 카메라별 프레임 캐시 (복사본)
        self.frame_buf_cache = [None] * 4  # 각 카메라별 프레임 버퍼 데이터 캐시
    
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

    async def save_image(self, camera_id: int, save_path: str, frame: int):
        try:
            if camera_id < 0 or camera_id >= 4:
                print(f"Invalid camera_id: {camera_id}")
                return False
                
            self.is_capturing[camera_id] = True
            self.max_frames = frame  # 최대 프레임 수
            frame_count = 0
            while frame_count < self.max_frames and self.is_capturing[camera_id]:
                
                if self.stOutFrames[camera_id] is None or self.cams[camera_id] is None:
                    print(f"Camera {camera_id} or frame not available")
                    self.is_capturing[camera_id] = False
                    return False

                # 프레임 복사본 만들기
                temp_frame = MV_FRAME_OUT()
                memmove(byref(temp_frame), byref(self.stOutFrames[camera_id]), sizeof(MV_FRAME_OUT))

                # 이미지 저장
                ret = save_non_raw_image(
                    save_type=1,  # JPEG 형식
                    frame_info=temp_frame,
                    cam_instance=self.cams[camera_id],
                    save_path=save_path+"/",
                    frame_number=frame_count  # frame_number 전달
                )

                if ret == 0:
                    print(f"Camera {camera_id}: Saved frame {frame_count + 1}/{self.max_frames}")
                    frame_count += 1
                else:
                    print(f"Camera {camera_id}: Failed to save frame {frame_count + 1}: ret[0x{ret:x}]")
                    self.is_capturing[camera_id] = False  # 저장 실패 시 캡처 중지
                    return False

                await asyncio.sleep(0.01)  
                
            self.is_capturing[camera_id] = False
            return True

        except Exception as e:
            print(f"Error in save_image for camera {camera_id}: {e}")
            self.is_capturing[camera_id] = False  # 에러 발생 시 캡처 중지
            return False

    async def get_frame(self, camera_id: int):
        try:
            if camera_id < 0 or camera_id >= 4:
                return None
                
            if self.cams[camera_id] is None:
                return None

            # 락을 사용하여 프레임 접근 동기화
            async with self.frame_locks[camera_id]:
                # 캐시된 프레임 정보 사용
                if self.frame_cache[camera_id] is None or \
                   self.frame_buf_cache[camera_id] is None:
                    return None
                
                # 프레임 정보가 유효한지 확인
                if self.frame_cache[camera_id].pBufAddr is None:
                    return None
                
                # 프레임 정보 복사 (락 내에서)
                frame_info = MV_FRAME_OUT_INFO_EX()
                cdll.msvcrt.memcpy(byref(frame_info), 
                                  byref(self.frame_cache[camera_id].stFrameInfo), 
                                  sizeof(MV_FRAME_OUT_INFO_EX))
                
                # 버퍼 데이터 복사 (락 내에서)
                frame_len = frame_info.nFrameLen
                if frame_len > 0:
                    temp_buf = (c_ubyte * frame_len)()
                    cdll.msvcrt.memcpy(temp_buf, 
                                      self.frame_buf_cache[camera_id], 
                                      frame_len)
                else:
                    return None
            
            # 락 밖에서 프레임 처리 (블로킹 방지)
            # 복사된 버퍼를 SDK 함수에 전달하여 RGB 변환
            loop = asyncio.get_event_loop()
            frame_data = await loop.run_in_executor(
                None, 
                take_frame_from_buffer, 
                frame_info,
                temp_buf,
                self.cams[camera_id]
            )
            if frame_data is not None:
                return frame_data
            return None

        except Exception as e:
            # 에러 로그는 필요할 때만 출력 (너무 많은 로그 방지)
            return None
    
    async def get_frame_save(self, camera_id: int, save_path=None):
        try:
            if camera_id < 0 or camera_id >= 4:
                return None
                
            if self.stOutFrames[camera_id] is None or self.cams[camera_id] is None:
                return None

            # 프레임 버퍼가 유효한지 확인
            if self.stOutFrames[camera_id].pBufAddr is None:
                return None

            # 동기 함수를 비동기로 실행하여 블로킹 방지
            loop = asyncio.get_event_loop()
            frame_data = await loop.run_in_executor(
                None, 
                take_frame_save, 
                self.stOutFrames[camera_id], 
                self.cams[camera_id],
                save_path
            )
            if frame_data is not None:
                return frame_data

            return None

        except Exception as e:
            # 에러 로그는 필요할 때만 출력 (너무 많은 로그 방지)
            return None
        
    async def set_feature(self, camera_id: int, fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format):
        try:
            if camera_id < 0 or camera_id >= 4:
                print(f"Invalid camera_id: {camera_id}")
                return None
                
            if self.cams[camera_id] is None:
                print(f"Camera {camera_id} not available")
                return None

            settings = set_camera_settings(self.cams[camera_id], fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format)
            if settings is None:
                return None

            return True

        except Exception as e:
            print(f"Error setting features for camera {camera_id}: {e}")
            return None

    async def get_feature(self, camera_id: int):
        try:
            if camera_id < 0 or camera_id >= 4:
                print(f"Invalid camera_id: {camera_id}")
                return None
                
            if self.cams[camera_id] is None:
                print(f"Camera {camera_id} not available")
                return None

            settings = get_camera_settings(self.cams[camera_id])
            if settings is None:
                return None

            formatted_settings = {}
            for key, value in settings.items():
                if isinstance(value, (int, float)):
                    formatted_settings[key] = value
                else:
                    formatted_settings[key] = str(value)

            return formatted_settings

        except Exception as e:
            print(f"Error getting features for camera {camera_id}: {e}")
            return None

    async def get_device_list(self):
        """디바이스 리스트를 반환하는 함수"""
        try:
            # SDK 초기화 (이미 초기화되어 있으면 스킵)
            ret = await asyncio.to_thread(MvCamera.MV_CC_Initialize)
            if ret != 0:
                print(f"SDK Initialize fail! ret[0x{ret:x}]")
                return None

            deviceList = MV_CC_DEVICE_INFO_LIST()
            tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE
            ret = await asyncio.to_thread(MvCamera.MV_CC_EnumDevices, tlayerType, deviceList)
            if ret != 0:
                print(f"Enum devices fail! ret[0x{ret:x}]")
                return None

            if deviceList.nDeviceNum == 0:
                print("No device found!")
                return []

            devices = []
            for i in range(0, deviceList.nDeviceNum):
                mvcc_dev_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                
                # 모델명 추출
                strModeName = ""
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chModelName:
                    if per == 0:
                        break
                    strModeName = strModeName + chr(per)
                
                # IP 주소 추출
                nip1 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
                nip2 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
                nip3 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
                nip4 = (mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
                ip_address = f"{nip1}.{nip2}.{nip3}.{nip4}"
                
                # MAC 주소 추출
                mac_address = ""
                try:
                    mac_bytes = mvcc_dev_info.SpecialInfo.stGigEInfo.chMACAddr
                    if mac_bytes:
                        mac_parts = []
                        for j in range(6):
                            if j < len(mac_bytes):
                                mac_parts.append(f"{mac_bytes[j]:02x}")
                        mac_address = ":".join(mac_parts)
                except:
                    mac_address = "N/A"
                
                # Serial Number 추출
                serial_number = ""
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chSerialNumber:
                    if per == 0:
                        break
                    serial_number = serial_number + chr(per)
                
                # User Name 추출
                user_name = ""
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chUserDefinedName:
                    if per == 0:
                        break
                    user_name = user_name + chr(per)
                
                device_info = {
                    "device_index": i,
                    "model_name": strModeName,
                    "ip_address": ip_address,
                    "mac_address": mac_address if mac_address else "N/A",
                    "serial_number": serial_number if serial_number else "N/A",
                    "user_name": user_name if user_name else "N/A",
                    "device_type": "GigE"  # 현재는 GigE만 지원
                }
                devices.append(device_info)
                
            return devices

        except Exception as e:
            print(f"Error getting device list: {str(e)}")
            return None

    async def work_thread(self, camera_id: int):
        if camera_id < 0 or camera_id >= 4:
            print(f"Invalid camera_id: {camera_id}")
            return
            
        self.stOutFrames[camera_id] = MV_FRAME_OUT()  
        memset(byref(self.stOutFrames[camera_id]), 0, sizeof(self.stOutFrames[camera_id]))
        
        while True:
            try:
                if self.cams[camera_id] is None:
                    await asyncio.sleep(1)
                    continue
                    
                ret = self.cams[camera_id].MV_CC_GetImageBuffer(self.stOutFrames[camera_id], 1000)  
                if None != self.stOutFrames[camera_id].pBufAddr and 0 == ret:
                    # 프레임 정보와 버퍼 데이터를 캐시에 복사 (get_frame에서 사용할 수 있도록)
                    async with self.frame_locks[camera_id]:
                        # 프레임 정보 복사
                        if self.frame_cache[camera_id] is None:
                            self.frame_cache[camera_id] = MV_FRAME_OUT()
                        
                        # 프레임 정보 복사 (메타데이터)
                        cdll.msvcrt.memcpy(byref(self.frame_cache[camera_id].stFrameInfo), 
                                          byref(self.stOutFrames[camera_id].stFrameInfo), 
                                          sizeof(MV_FRAME_OUT_INFO_EX))
                        
                        # 버퍼 데이터 복사 (실제 이미지 데이터)
                        frame_len = self.stOutFrames[camera_id].stFrameInfo.nFrameLen
                        if frame_len > 0:
                            # 버퍼가 필요하면 재할당
                            if self.frame_buf_cache[camera_id] is None or \
                               len(self.frame_buf_cache[camera_id]) < frame_len:
                                self.frame_buf_cache[camera_id] = (c_ubyte * frame_len)()
                            
                            # 실제 버퍼 데이터 복사
                            cdll.msvcrt.memcpy(self.frame_buf_cache[camera_id], 
                                              self.stOutFrames[camera_id].pBufAddr, 
                                              frame_len)
                            
                            # 프레임 정보에 복사된 버퍼 주소 설정 (POINTER(c_ubyte) 타입)
                            self.frame_cache[camera_id].pBufAddr = cast(self.frame_buf_cache[camera_id], POINTER(c_ubyte))
                            # stFrameInfo는 이미 복사되었으므로 다시 할당할 필요 없음
                    
                    # 프레임 버퍼 해제 (원본은 해제하지만 캐시는 유지)
                    nRet = self.cams[camera_id].MV_CC_FreeImageBuffer(self.stOutFrames[camera_id])
                else:
                    error_msg = self._get_error_message(ret)
                    print(f"Camera {camera_id}: no data[0x{ret:x}] ({error_msg})")                

                await asyncio.sleep(0.1)  # 프레임 캡처 간격
                
            except Exception as e:
                print(f"Error in work thread for camera {camera_id}: {e}")
                await asyncio.sleep(1)

    async def cleanup_cameras(self):
        """모든 카메라를 닫고 정리하는 함수"""
        print("Cleaning up existing camera connections...")
        for camera_id in range(4):
            if self.cams[camera_id] is not None:
                try:
                    # 카메라가 열려있는지 확인하고 닫기
                    try:
                        await asyncio.to_thread(self.cams[camera_id].MV_CC_CloseDevice)
                    except:
                        pass
                    # Handle 정리
                    try:
                        await asyncio.to_thread(self.cams[camera_id].MV_CC_DestroyHandle)
                    except:
                        pass
                    self.cams[camera_id] = None
                    print(f"Camera {camera_id} cleaned up")
                except Exception as e:
                    print(f"Error cleaning up camera {camera_id}: {e}")
        # SDK 정리
        try:
            await asyncio.to_thread(MvCamera.MV_CC_Finalize)
        except:
            pass
        await asyncio.sleep(0.5)  # 정리 후 잠시 대기

    async def initialize(self):
        try:
            # 기존 카메라 연결 정리
            await self.cleanup_cameras()
            
            ret = await asyncio.to_thread(MvCamera.MV_CC_Initialize)
            if ret != 0:
                print(f"SDK Initialize fail! ret[0x{ret:x}]")
                return False

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
            
            # 디바이스 리스트와 IP 정보 수집
            device_info_list = []
            for i in range(0, deviceList.nDeviceNum):
                mvcc_dev_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                print("\ngige device: [%d]" % i)
                strModeName = ""
                for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chModelName:
                    if per == 0:
                        break
                    strModeName = strModeName + chr(per)
                print("device model name: %s" % strModeName)

                nip1 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
                nip2 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
                nip3 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
                nip4 = (mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
                ip_address = f"{nip1}.{nip2}.{nip3}.{nip4}"
                print("current ip: %s\n" % ip_address)
                
                device_info_list.append({
                    'device_index': i,
                    'device_info': mvcc_dev_info,
                    'ip_address': ip_address
                })

            # DB에서 카메라 IP 매핑 정보 가져오기
            camera_ip_mapping = {}  # {camera_id: ip_address}
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get("http://localhost:8000/camera/get_feature")
                    if response.status_code == 200:
                        camera_features = response.json()
                        for feature in camera_features:
                            camera_number = feature.get('CAMERA')  # 1-4
                            ip_address = feature.get('IP')
                            if camera_number and ip_address:
                                camera_id = camera_number - 1  # 0-3으로 변환
                                camera_ip_mapping[camera_id] = ip_address
                                print(f"DB Mapping: Camera {camera_id} (UI: {camera_number}) -> IP: {ip_address}")
                    else:
                        print(f"Failed to get camera features from DB: {response.status_code}")
            except Exception as e:
                print(f"Error fetching camera IP mapping from DB: {e}")
                print("Proceeding with default index-based mapping")

            # IP 매핑 기반으로 디바이스 인덱스 매핑 생성
            # {camera_id: device_index}
            camera_to_device_mapping = {}
            used_device_indices = set()
            
            # 1. DB에 IP가 있는 카메라부터 매핑
            for camera_id in range(4):
                if camera_id in camera_ip_mapping:
                    target_ip = camera_ip_mapping[camera_id]
                    # 해당 IP를 가진 디바이스 찾기
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
                    # 아직 사용되지 않은 디바이스 찾기
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

            # 최대 4개 카메라 초기화 (매핑된 순서대로)
            max_cameras = min(4, len(camera_to_device_mapping))
            initialized_count = 0
            
            for camera_id in range(max_cameras):
                if camera_id not in camera_to_device_mapping:
                    print(f"Camera {camera_id} has no device mapping, skipping...")
                    continue
                    
                device_index = camera_to_device_mapping[camera_id]
                try:
                    self.cams[camera_id] = MvCamera()
                    stDeviceList = cast(deviceList.pDeviceInfo[device_index], 
                                      POINTER(MV_CC_DEVICE_INFO)).contents
                    ret = await asyncio.to_thread(self.cams[camera_id].MV_CC_CreateHandle, stDeviceList)
                    if ret != 0:
                        print(f"Camera {camera_id}: Create handle fail! ret[0x{ret:x}]")
                        self.cams[camera_id] = None
                        continue

                    # OpenDevice 재시도 로직 (최대 3회)
                    max_retries = 3
                    retry_delay = 0.5
                    open_success = False
                    
                    for retry in range(max_retries):
                        ret = await asyncio.to_thread(self.cams[camera_id].MV_CC_OpenDevice, MV_ACCESS_Exclusive, 0)
                        if ret == 0:
                            open_success = True
                            break
                        else:
                            error_msg = self._get_error_message(ret)
                            if ret == 0x80000203:  # MV_E_ACCESS_DENIED
                                print(f"Camera {camera_id}: Open device fail (Access Denied) - Device may be already opened. Retry {retry + 1}/{max_retries}...")
                                # 이전 핸들 정리 후 재시도
                                try:
                                    await asyncio.to_thread(self.cams[camera_id].MV_CC_DestroyHandle)
                                except:
                                    pass
                                await asyncio.sleep(retry_delay)
                                # 새 핸들 생성
                                self.cams[camera_id] = MvCamera()
                                ret = await asyncio.to_thread(self.cams[camera_id].MV_CC_CreateHandle, stDeviceList)
                                if ret != 0:
                                    print(f"Camera {camera_id}: Create handle fail on retry! ret[0x{ret:x}]")
                                    break
                            else:
                                print(f"Camera {camera_id}: Open device fail! ret[0x{ret:x}] ({error_msg})")
                                if retry < max_retries - 1:
                                    await asyncio.sleep(retry_delay)
                    
                    if not open_success:
                        print(f"Camera {camera_id}: Failed to open device after {max_retries} retries")
                        try:
                            await asyncio.to_thread(self.cams[camera_id].MV_CC_DestroyHandle)
                        except:
                            pass
                        self.cams[camera_id] = None
                        continue
                    
                    # 카메라 간 초기화 지연 (리소스 충돌 방지)
                    await asyncio.sleep(0.2)

                    nPacketSize = await asyncio.to_thread(self.cams[camera_id].MV_CC_GetOptimalPacketSize)
                    if int(nPacketSize) > 0:
                        ret = await asyncio.to_thread(self.cams[camera_id].MV_CC_SetIntValue, "GevSCPSPacketSize", nPacketSize)
                        if ret != 0:
                            print(f"Camera {camera_id}: Warning: Set packet size fail! ret[0x{ret:x}]")

                    ret = await asyncio.to_thread(self.cams[camera_id].MV_CC_SetEnumValue, "TriggerMode", MV_TRIGGER_MODE_OFF)
                    if ret != 0:
                        print(f"Camera {camera_id}: Set trigger mode fail! ret[0x{ret:x}]")
                        await asyncio.to_thread(self.cams[camera_id].MV_CC_DestroyHandle)
                        self.cams[camera_id] = None
                        continue

                    ret = await asyncio.to_thread(self.cams[camera_id].MV_CC_StartGrabbing)
                    if ret != 0:
                        print(f"Camera {camera_id}: Start grabbing fail! ret[0x{ret:x}]")
                        await asyncio.to_thread(self.cams[camera_id].MV_CC_DestroyHandle)
                        self.cams[camera_id] = None
                        continue

                    print(f"Camera {camera_id} initialized successfully")
                    initialized_count += 1
                    
                except Exception as e:
                    print(f"Error initializing camera {camera_id}: {str(e)}")
                    if self.cams[camera_id]:
                        await asyncio.to_thread(self.cams[camera_id].MV_CC_DestroyHandle)
                        self.cams[camera_id] = None

            if initialized_count == 0:
                print("No cameras initialized successfully")
                return False
                
            print(f"Total {initialized_count} camera(s) initialized successfully")
            return True

        except Exception as e:
            print(f"Error initializing cameras: {str(e)}")
            # 실패한 카메라들 정리
            for i in range(4):
                if self.cams[i]:
                    try:
                        await asyncio.to_thread(self.cams[i].MV_CC_DestroyHandle)
                    except:
                        pass
                    self.cams[i] = None
            return False

    async def restart(self):
        try:
            print("Restarting camera...")
            await self.stop_grabbing()            
            self.__init__()            
            success = await self.start_grabbing()
            if success:
                print("Camera restarted successfully")
                return True
            else:
                print("Failed to restart camera")
                return False
        except Exception as e:
            print(f"Error restarting camera: {str(e)}")
            return False
        
    async def start_grabbing(self):
        try:
            if not await self.initialize():
                print("Failed to initialize cameras")
                return False

            print("Camera grabbing started...")
            # 각 카메라별로 work_thread 태스크 생성
            for camera_id in range(4):
                if self.cams[camera_id] is not None:
                    self.grab_tasks[camera_id] = asyncio.create_task(self.work_thread(camera_id))
            self.is_running = True  # 상태 업데이트
            return True
                
        except Exception as e:
            print(f"Error starting grabbing: {str(e)}")
            self.is_running = False  # 실패 시 상태 업데이트
            return False

    async def stop_grabbing(self):
        try:            
            self.is_running = False  # 상태 업데이트
            
            # 모든 grab 태스크 취소
            for camera_id in range(4):
                if self.grab_tasks[camera_id] is not None:
                    self.grab_tasks[camera_id].cancel()
                    try:
                        await self.grab_tasks[camera_id]
                    except asyncio.CancelledError:
                        pass
                    self.grab_tasks[camera_id] = None

            # 모든 카메라 정리
            for camera_id in range(4):
                if self.cams[camera_id] is not None:
                    try:
                        ret = self.cams[camera_id].MV_CC_StopGrabbing()
                        if ret != 0:
                            print(f"Camera {camera_id}: stop grabbing fail! ret[0x{ret:x}]")

                        ret = self.cams[camera_id].MV_CC_CloseDevice()
                        if ret != 0:
                            print(f"Camera {camera_id}: close device fail! ret[0x{ret:x}]")
                        
                        self.cams[camera_id].MV_CC_DestroyHandle()
                    except Exception as e:
                        print(f"Error stopping camera {camera_id}: {e}")
                    finally:
                        self.cams[camera_id] = None
                        self.stOutFrames[camera_id] = None
                        
            MvCamera.MV_CC_Finalize()
            
            print("All cameras and work threads stopped successfully")
            return True
        except Exception as e:
            print(f"Error stopping grabbing: {str(e)}")
            return False

    async def get_status(self, camera_id: int = None):
        """카메라 상태 반환 (camera_id가 None이면 모든 카메라 상태 반환)"""
        try:
            if camera_id is not None:
                if camera_id < 0 or camera_id >= 4:
                    return None
                return {
                    "camera_id": camera_id,
                    "is_running": self.is_running,
                    "has_camera": self.cams[camera_id] is not None,
                    "is_grabbing": self.grab_tasks[camera_id] is not None and not self.grab_tasks[camera_id].done() if self.grab_tasks[camera_id] else False
                }
            else:
                # 모든 카메라 상태 반환
                status_list = []
                for i in range(4):
                    status_list.append({
                        "camera_id": i,
                        "is_running": self.is_running,
                        "has_camera": self.cams[i] is not None,
                        "is_grabbing": self.grab_tasks[i] is not None and not self.grab_tasks[i].done() if self.grab_tasks[i] else False
                    })
                return {
                    "is_running": self.is_running,
                    "cameras": status_list
                }
        except Exception as e:
            print(f"Error getting camera status: {e}")
            return None

# 전역 인스턴스 생성
cameragrab = CameraGrab()

async def start_grabbing():
    await cameragrab.restart()

async def stop_grabbing():
    await cameragrab.stop_grabbing()

async def save_image(camera_id: int, save_path: str, frame: int):
    return await cameragrab.save_image(camera_id, save_path, frame) 

async def get_frame(camera_id: int):
    return await cameragrab.get_frame(camera_id)

async def get_frame_save(camera_id: int, save_path=None):
    return await cameragrab.get_frame_save(camera_id, save_path)

async def set_feature(camera_id: int, fpsenable: int, fps: float, gainauto: int, gain: float, exposuretime: float, width: int, height: int, pixel_format: int):
    return await cameragrab.set_feature(camera_id, fpsenable, fps, gainauto, gain, exposuretime, width, height, pixel_format)

async def get_feature(camera_id: int):
    return await cameragrab.get_feature(camera_id)

async def get_camera_status(camera_id: int = None):
    return await cameragrab.get_status(camera_id)

async def get_device_list():
    return await cameragrab.get_device_list()

if __name__ == "__main__":
    async def main():
        # 카메라 시작
        start_task = asyncio.create_task(start_grabbing())

        async def save_loop2():
            while True:
                try:
                    await save_image("saved_images")
                    await asyncio.sleep(4)
                except Exception as e:
                    print(f"Error grabbing image: {e}")
                    await asyncio.sleep(2)

        # 저장 태스크 시작
        save_task2 = asyncio.create_task(save_loop2())
        try:
            # 두 태스크 모두 실행
            await asyncio.gather(start_task, save_task2)
        except KeyboardInterrupt:
            print("\nStopping camera...")

        finally:
            # 정리
            await stop_grabbing()

    # 메인 실행
    asyncio.run(main())
