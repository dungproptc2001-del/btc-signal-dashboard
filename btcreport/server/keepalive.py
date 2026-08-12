"""Giữ máy không ngủ trong lúc server chạy.

Máy này dùng S0 Modern Standby, mặc định ngủ sau 5 phút khi cắm điện. Ngủ là Windows
treo tiến trình desktop → web sập. Task Scheduler không giữ thức được, nó chỉ đánh
thức máy đúng giờ hẹn.

Cách làm ở đây là API chính thống của Windows: tiến trình tự khai báo "đang cần hệ
thống thức". Ưu điểm so với sửa power plan bằng powercfg:

  - Chỉ giữ thức ĐÚNG LÚC server chạy. Tắt server là máy về nếp cũ ngay lập tức.
  - Không đụng cấu hình hệ thống, không cần quyền admin.
  - Gỡ project đi không để lại dấu vết gì.

Không xin ES_DISPLAY_REQUIRED nên màn hình vẫn tự tắt bình thường.
Kiểm chứng đang có hiệu lực: `powercfg /requests`
"""
import atexit
import ctypes
import sys

ES_CONTINUOUS       = 0x80000000
ES_SYSTEM_REQUIRED  = 0x00000001

_held = False


def available():
    return sys.platform == "win32"


def hold():
    """Bắt đầu giữ máy thức. Trả True nếu thành công."""
    global _held
    if not available():
        print("  [keepalive] Không phải Windows – bỏ qua.")
        return False
    try:
        r = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        if r == 0:
            print("  [keepalive] Windows từ chối yêu cầu.")
            return False
        _held = True
        atexit.register(release)
        print("  [keepalive] Máy sẽ không ngủ khi server còn chạy "
              "(màn hình vẫn tắt bình thường).")
        return True
    except Exception as e:
        print(f"  [keepalive] Lỗi: {e}")
        return False


def release():
    """Nhả quyền giữ thức, máy trở lại nếp ngủ bình thường."""
    global _held
    if not _held or not available():
        return
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        _held = False
        print("  [keepalive] Đã nhả – máy ngủ lại bình thường.")
    except Exception as e:
        print(f"  [keepalive] Lỗi lúc nhả: {e}")


def is_held():
    return _held
