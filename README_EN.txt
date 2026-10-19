STACK DUEL — Windows / Dash LAN Edition
=======================================

QUICK START
-----------
1. Extract the ZIP file to a folder of your choice.
2. Install Python 3.10 or newer on your Windows PC:
   https://www.python.org/downloads/windows/
   Enabling "Add python.exe to PATH" during installation is recommended.
3. Double-click Start_Stack_Duel.bat.
   On the first run, the script creates a local virtual environment (.venv)
   and installs the required packages (Dash, qrcode, and Pillow).
   Internet access is needed for this first-time installation.
4. Open http://localhost:8050 on the PC. The batch file also attempts to
   open this address automatically in your default browser.
5. The PC screen shows a separate QR code for each player. Connect your
   Android phones to the same Wi-Fi or LAN as the PC, then scan the QR codes.

HOW TO PLAY — ENDLESS MODE
--------------------------
- One connected phone: SOLO MODE. The same player takes every turn.
- Two connected phones: DUEL MODE. Players 1 and 2 alternate turns on
  the SAME tower.
- Tap the TAP! area on your phone to place the moving block.
- Any area extending beyond the existing stack is cut off and counted
  against the player who placed that block.
- In Duel Mode, the player with the LOWER total wasted area wins when
  the tower is missed completely. The player who misses loses the full
  remaining platform area, which counts as wasted area.
- Click NEW MATCH on the PC to restart.
- ENDLESS MODE: There is no placement limit. Keep stacking until a block
  completely misses the tower. A full miss ends the game.
- If the second phone connects or disconnects mid-game, the mode changes
  while the existing tower is retained.

IF YOUR PHONE CANNOT CONNECT
----------------------------
A. Check that the phone and PC can communicate over the same network.
   Guest Wi-Fi networks sometimes block communication between devices.
B. Allow incoming connections to Python on TCP port 8050 in Windows
   Defender Firewall if Windows prompts you to do so. Use only a trusted
   private network.
C. Open Command Prompt and run: ipconfig
   Find the PC's IPv4 address under the active Wi-Fi or Ethernet adapter.
   In Start_Stack_Duel.bat, remove REM from the following line and replace
   the sample IP with your PC's actual IPv4 address:
       REM set "STACK_PUBLIC_HOST=192.168.1.100"
   For example:
       set "STACK_PUBLIC_HOST=192.168.1.100"
   Restart the server to refresh the QR code URLs.
D. As another test, enter http://YOUR_PC_IP:8050 directly in your phone's
   browser (replace YOUR_PC_IP with the real IPv4 address).
E. If port 8050 is already in use, change STACK_PORT in the BAT file.

DIFFICULTY SETTINGS
-------------------
Edit these lines in Start_Stack_Duel.bat:

  set "STACK_BASE_SPEED=2.0"     Initial movement speed (previously 1.3)
  set "STACK_SPEED_GAIN=0.32"    Speed increase per level (previously 0.11)
  set "STACK_EXTRA_AFTER=12"    Level after which extra acceleration applies
  set "STACK_EXTRA_GAIN=0.20"  Extra speed increase per later level

For a harder game, try STACK_BASE_SPEED=2.5 and STACK_SPEED_GAIN=0.45.
Save the BAT file and restart the server to apply changes.

NOTES
-----
- Game state lives in the memory of the Python process running on the PC.
- Closing the browser does not reset the game while the server is running.
- Press Ctrl+C in the command window to stop the server.
- Phone connection detection uses a timeout of approximately 4 seconds.
- This is a simple local-network game. It has no authentication or
  protection against someone else using a player's control URL.
  Avoid sharing the player QR codes outside your trusted network.
- The Python source has passed a syntax check, but Windows/Android
  end-to-end testing has not been completed by the developer.

ENDLESS DISPLAY
---------------
- The PC game view follows the top of the tower, displaying the most
  recent 28 layers for readability. Earlier layers are still counted.
- Movement speed continues increasing with levels. Modify difficulty in
  the BAT file if extremely high levels become too fast.
