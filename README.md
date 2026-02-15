# 🎮 Discord Minigame Bot

Bot Discord hỗ trợ nhiều minigame với kiến trúc mở rộng dễ dàng.

## ✨ Tính năng

- **Quản lý State**: Sử dụng Enum để quản lý trạng thái game rõ ràng
- **Kiến trúc mở rộng**: Dễ dàng thêm game mới thông qua kế thừa `BaseGame`
- **Game Factory Pattern**: Tạo game linh hoạt
- **Event Logging**: Ghi log tất cả sự kiện trong game
- **Discord Slash Commands**: Sử dụng commands hiện đại của Discord

## 🎲 Game hiện có

### 1. Lì Xì Ngày Tết
Game đấu tuổi theo phong tục Việt Nam:
- Người chơi bắt đầu với M đồng
- Mỗi ngày random tuổi từ 1 đến 2N
- Đấu với nhau, người lớn tuổi phải lì xì
- Nếu hiệu tuổi > N: người lớn tuổi → coi như nhỏ tuổi
- Mỗi cặp chỉ đấu 1 lần/ngày

## 📋 Yêu cầu

- Python 3.8+
- discord.py 2.3.0+
- Bot Discord với Privileged Gateway Intents enabled

## 🚀 Cài đặt

1. **Clone repository**
```bash
git clone <your-repo>
cd discord-minigame-bot
```

2. **Cài đặt dependencies**
```bash
pip install -r requirements.txt
```

3. **Tạo Discord Bot**
- Truy cập [Discord Developer Portal](https://discord.com/developers/applications)
- Tạo New Application
- Vào Bot → Reset Token → Copy token
- Enable Privileged Gateway Intents:
  - PRESENCE INTENT
  - SERVER MEMBERS INTENT
  - MESSAGE CONTENT INTENT

4. **Cấu hình Bot**
```bash
cp .env.example .env
# Sửa DISCORD_BOT_TOKEN trong file .env
```

5. **Mời Bot vào Server**
- Vào OAuth2 → URL Generator
- Chọn scopes: `bot`, `applications.commands`
- Chọn permissions: 
  - Send Messages
  - Embed Links
  - Attach Files
  - Read Message History
  - Use Slash Commands
- Copy URL và mời bot vào server

6. **Chạy Bot**
```bash
python bot.py
```

## 📖 Hướng dẫn sử dụng

### Lệnh Host (chỉ người tạo game)

| Lệnh | Mô tả |
|------|-------|
| `/host <game_type>` | Tạo game mới |
| `/settinggame` | Chỉnh cài đặt game |
| `/setnotifchannel <channel>` | Set kênh thông báo |
| `/setgamechannel <channel>` | Set kênh chơi game |
| `/endregister` | Đóng đăng ký |
| `/startgame [delay]` | Bắt đầu game |
| `/pausegame` | Tạm dừng game |
| `/endgame` | Kết thúc game |
| `/log` | Xuất file log |

### Lệnh Người chơi

| Lệnh | Mô tả |
|------|-------|
| `/help [game_type]` | Xem hướng dẫn |
| `/rule <game_type>` | Xem luật chơi |
| `/joingame` | Tham gia game |
| `/leavegame` | Rời game |

### Lệnh Game: Lì Xì Ngày Tết

| Lệnh | Mô tả |
|------|-------|
| `/fight <opponent> <bet>` | Thách đấu người khác |
| `/stats` | Xem thông tin bản thân |
| `/reroll` | Random lại tuổi (1 lần/ngày) |
| `/leaderboard` | Xem bảng xếp hạng |

## 🎯 Quy trình chơi game

1. **Host tạo game**: `/host li_xi_ngay_tet`
2. **Cài đặt**: `/settinggame` → điền thông số
3. **Set channels**: 
   - `/setnotifchannel #announcements`
   - `/setgamechannel #game-room` (tùy chọn)
4. **Người chơi tham gia**: `/joingame`
5. **Đóng đăng ký**: `/endregister`
6. **Bắt đầu**: `/startgame`
7. **Chơi game**: Dùng các lệnh game
8. **Kết thúc**: `/endgame`

## 🔧 Cấu trúc code

```
bot.py
├── Enums (GameType, GameState, GameInterval)
├── BaseGame (Lớp cơ sở cho game)
│   ├── get_default_settings()
│   ├── validate_settings()
│   ├── on_game_start()
│   ├── on_game_end()
│   └── on_day_change()
├── LiXiNgayTetGame (Game cụ thể)
│   ├── fight()
│   ├── reroll_age()
│   └── get_leaderboard()
├── GameFactory (Tạo game)
└── MinigameBot (Discord Bot)
```

## ➕ Thêm game mới

1. **Thêm GameType enum**
```python
class GameType(Enum):
    YOUR_GAME = "your_game"
```

2. **Tạo class game mới**
```python
class YourGame(BaseGame):
    def get_default_settings(self) -> dict:
        return {"setting1": value1}
    
    def validate_settings(self, settings: dict) -> tuple[bool, str]:
        # Validate logic
        return True, ""
    
    async def on_game_start(self):
        # Init game
        pass
```

3. **Thêm vào GameFactory**
```python
@staticmethod
def create_game(game_type: GameType, host_id: int):
    if game_type == GameType.YOUR_GAME:
        return YourGame(host_id)
```

4. **Thêm commands cho game**
```python
@bot.tree.command(name="your_command")
async def your_command(interaction: discord.Interaction):
    if not isinstance(bot.current_game, YourGame):
        return
    # Command logic
```

## 📊 State Management

```
IDLE → REGISTERING → REGISTRATION_CLOSED → RUNNING → ENDED
                                              ↕
                                           PAUSED
```

## 🐛 Debug

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 Contributing

Mọi đóng góp đều được chào đón! Vui lòng:
1. Fork repo
2. Tạo branch mới
3. Commit changes
4. Push và tạo Pull Request

## 📝 License

MIT License

## 📧 Liên hệ

Nếu có vấn đề, hãy tạo Issue trên GitHub.

---

**Lưu ý**: Bot này dùng cho mục đích giải trí và học tập. Không khuyến khích đánh bạc thật.