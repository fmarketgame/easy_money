import pyautogui
import pyperclip
import time
import json

from pathlib import Path
from io import BytesIO
from PIL import Image
import win32clipboard


# =========================================================
# CONFIG
# =========================================================

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.20

MAX_RESPONSE_WAIT = 1800       # 30 minutes
INITIAL_RESPONSE_WAIT = 60     # let high-reasoning model work first
CHECK_INTERVAL = 10

# While ChatGPT is thinking, scroll every X seconds
SCROLL_INTERVAL = 10

# Negative = scroll downward
SCROLL_AMOUNT = -500

DEFAULT_ANCHOR_TIMEOUT = 20
DEFAULT_CONFIDENCE = 0.82


# =========================================================
# PATHS
# =========================================================

AGENT_FOLDER = Path(
    r"C:\Users\mimer\Desktop\DepopBot\Agent"
)

ANCHOR_FOLDER = (
    AGENT_FOLDER
    / "anchors"
)

PROMPT_FILE = (
    AGENT_FOLDER
    / "Depop_Master_Prompt_CSV_First.txt"
)

RAW_PHOTO_FOLDER = Path(
    r"C:\Users\mimer\Desktop\DepopBot\Inventory\DP-0001\raw_photos"
)

RAW_RESPONSE_FILE = (
    AGENT_FOLDER
    / "last_response_raw.txt"
)

JSON_RESPONSE_FILE = (
    AGENT_FOLDER
    / "last_response.json"
)

DEBUG_COPY_FILE = (
    AGENT_FOLDER
    / "last_copy_attempt.txt"
)

FAILURE_FOLDER = (
    AGENT_FOLDER
    / "failures"
)


# =========================================================
# VISUAL ANCHORS
# =========================================================

BOOKMARKS_FOLDER = (
    ANCHOR_FOLDER
    / "bookmarks_folder.png"
)

CHATGPT_BOOKMARK = (
    ANCHOR_FOLDER
    / "chatgpt_bookmark.png"
)

CHATGPT_TEXTBOX = (
    ANCHOR_FOLDER
    / "chatgpt_textbox.png"
)

COPY_RESPONSE = (
    ANCHOR_FOLDER
    / "copy_response.png"
)


# =========================================================
# BASIC UTILITIES
# =========================================================

def timestamp():
    return time.strftime("%Y%m%d_%H%M%S")


def save_failure_screenshot(name):
    FAILURE_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    path = (
        FAILURE_FOLDER
        / f"{timestamp()}_{name}.png"
    )

    pyautogui.screenshot(
        str(path)
    )

    return path


def validate_file(path, description):
    if not path.exists():
        raise FileNotFoundError(
            f"\nMissing {description}:\n{path}"
        )


# =========================================================
# OPEN CHROME THROUGH WINDOWS UI
# =========================================================

def open_chrome_via_start_menu():
    """
    Opens Chrome through the normal Windows Search UI.

    This avoids:
    - hardcoded taskbar coordinates
    - visual matching of the Chrome taskbar icon
    - subprocess/browser-driver launching

    It simply automates:
        Win+S -> type Google Chrome -> Enter
    """

    print("[WINDOWS] Opening Search...")

    pyautogui.hotkey(
        "win",
        "s"
    )

    time.sleep(1)

    print("[WINDOWS] Searching for Google Chrome...")

    pyautogui.write(
        "Google Chrome",
        interval=0.04
    )

    time.sleep(1)

    print("[WINDOWS] Launching Chrome...")

    pyautogui.press(
        "enter"
    )

    # Give Chrome time to become active.
    time.sleep(5)


# =========================================================
# VISUAL ANCHOR ENGINE
# =========================================================

def find_anchor(
    image_path,
    confidence=DEFAULT_CONFIDENCE
):
    """
    Return all matches for an anchor currently visible on screen.
    """

    try:
        return list(
            pyautogui.locateAllOnScreen(
                str(image_path),
                confidence=confidence
            )
        )

    except Exception as error:
        print(
            f"[VISION ERROR] "
            f"{image_path.name}: {error}"
        )
        return []


def wait_for_anchor(
    image_path,
    name,
    timeout=DEFAULT_ANCHOR_TIMEOUT,
    confidence=DEFAULT_CONFIDENCE,
    poll_interval=0.4
):
    """
    Wait until at least one visual match exists.
    Never guesses. If it cannot find the expected UI, it stops.
    """

    print(
        f"[VISION] Looking for {name}..."
    )

    start = time.time()

    while (
        time.time() - start
        < timeout
    ):
        matches = find_anchor(
            image_path,
            confidence=confidence
        )

        if matches:
            print(
                f"[VISION] Found {name} "
                f"({len(matches)} match(es))."
            )
            return matches

        time.sleep(
            poll_interval
        )

    screenshot = save_failure_screenshot(
        f"FAILED_{name}"
    )

    raise TimeoutError(
        f"\nCould not find {name} after "
        f"{timeout} seconds.\n"
        f"Anchor:\n{image_path}\n\n"
        f"Failure screenshot:\n{screenshot}"
    )


def click_anchor(
    image_path,
    name,
    timeout=DEFAULT_ANCHOR_TIMEOUT,
    confidence=DEFAULT_CONFIDENCE,
    choose="first",
    pause_after=1.0
):
    """
    Locate a UI element visually and click its center.

    choose:
        first   -> first match
        lowest  -> lowest visible match
        highest -> highest visible match
    """

    matches = wait_for_anchor(
        image_path=image_path,
        name=name,
        timeout=timeout,
        confidence=confidence
    )

    if choose == "lowest":
        match = max(
            matches,
            key=lambda box: box.top
        )

    elif choose == "highest":
        match = min(
            matches,
            key=lambda box: box.top
        )

    else:
        match = matches[0]

    center = pyautogui.center(
        match
    )

    print(
        f"[CLICK] {name}: "
        f"X={center.x}, Y={center.y}"
    )

    pyautogui.click(
        center.x,
        center.y
    )

    time.sleep(
        pause_after
    )

    return center


# =========================================================
# IMAGE -> WINDOWS CLIPBOARD
# =========================================================

def copy_image_to_clipboard(image_path):
    image = Image.open(
        image_path
    )

    if image.mode != "RGB":
        image = image.convert(
            "RGB"
        )

    output = BytesIO()

    image.save(
        output,
        "BMP"
    )

    # Windows clipboard CF_DIB expects BMP data
    # without the 14-byte BMP file header.
    dib_data = (
        output.getvalue()[14:]
    )

    output.close()

    win32clipboard.OpenClipboard()

    try:
        win32clipboard.EmptyClipboard()

        win32clipboard.SetClipboardData(
            win32clipboard.CF_DIB,
            dib_data
        )

    finally:
        win32clipboard.CloseClipboard()


# =========================================================
# FIND *_001 PHOTO
# =========================================================

def find_test_photo():
    valid_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp"
    }

    matches = [
        file
        for file
        in RAW_PHOTO_FOLDER.iterdir()

        if file.is_file()

        and file.suffix.lower()
        in valid_extensions

        and file.stem.endswith(
            "_001"
        )
    ]

    if not matches:
        raise FileNotFoundError(
            "\nNo photo ending in _001 "
            "was found inside:\n"
            f"{RAW_PHOTO_FOLDER}"
        )

    matches.sort()

    return matches[0]


# =========================================================
# JSON CLEANUP
# =========================================================

def clean_json_text(response_text):
    cleaned = (
        response_text.strip()
    )

    # Strip accidental Markdown fences.
    if cleaned.startswith("```"):
        lines = (
            cleaned.splitlines()
        )

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip()
            == "```"
        ):
            lines = lines[:-1]

        cleaned = (
            "\n".join(lines).strip()
        )

    # Extract outermost JSON object if there
    # is accidental prose around it.
    first_brace = cleaned.find(
        "{"
    )

    last_brace = cleaned.rfind(
        "}"
    )

    if (
        first_brace != -1
        and last_brace != -1
        and last_brace > first_brace
    ):
        cleaned = cleaned[
            first_brace:
            last_brace + 1
        ]

    return cleaned


# =========================================================
# COPY / RESPONSE ENGINE
# =========================================================

def try_copy_valid_response():
    """
    Locate the newest visible ChatGPT response Copy button,
    copy the response, parse it, and verify expected structure.
    """

    matches = find_anchor(
        COPY_RESPONSE,
        confidence=0.82
    )

    if not matches:
        print(
            "[RESPONSE] No Copy button "
            "currently visible."
        )
        return None

    newest = max(
        matches,
        key=lambda box: box.top
    )

    center = pyautogui.center(
        newest
    )

    print(
        f"[RESPONSE] Found "
        f"{len(matches)} Copy button(s)."
    )

    print(
        "[RESPONSE] Trying lowest button at "
        f"X={center.x}, Y={center.y}"
    )

    # Sentinel proves that clicking Copy
    # actually changed the clipboard.
    pyperclip.copy(
        "__WAITING_FOR_CHATGPT_COPY__"
    )

    pyautogui.click(
        center.x,
        center.y
    )

    time.sleep(2)

    response_text = (
        pyperclip.paste()
    )

    if (
        response_text
        == "__WAITING_FOR_CHATGPT_COPY__"
    ):
        print(
            "[RESPONSE] Copy was clicked, "
            "but clipboard did not change."
        )
        return None

    if not response_text.strip():
        print(
            "[RESPONSE] Clipboard was empty."
        )
        return None

    DEBUG_COPY_FILE.write_text(
        response_text,
        encoding="utf-8"
    )

    print("")
    print(
        "========== COPIED TEXT PREVIEW =========="
    )
    print(
        response_text[:1200]
    )
    print(
        "========================================="
    )
    print("")

    cleaned = clean_json_text(
        response_text
    )

    try:
        data = json.loads(
            cleaned
        )

    except json.JSONDecodeError as error:
        print(
            "[RESPONSE] JSON parse failed:"
        )
        print(
            error
        )
        return None

    if not isinstance(
        data,
        dict
    ):
        print(
            "[RESPONSE] JSON top level "
            "is not an object."
        )
        return None

    csv_fields = data.get(
        "csv_fields"
    )

    market_summary = data.get(
        "market_summary"
    )

    if not isinstance(
        csv_fields,
        dict
    ):
        print(
            "[RESPONSE] Missing "
            "'csv_fields'."
        )
        print(
            "[RESPONSE] Top-level keys:",
            list(data.keys())
        )
        return None

    if not isinstance(
        market_summary,
        dict
    ):
        print(
            "[RESPONSE] Missing "
            "'market_summary'."
        )
        print(
            "[RESPONSE] Top-level keys:",
            list(data.keys())
        )
        return None

    required_csv_keys = {
        "Description",
        "Category",
        "Price",
        "Brand",
        "Condition",
        "Size",
        "Color 1",
        "Color 2",
        "Source 1",
        "Source 2",
        "Age",
        "Style 1",
        "Style 2",
        "Style 3"
    }

    missing = (
        required_csv_keys
        - set(csv_fields.keys())
    )

    if missing:
        print(
            "[RESPONSE] JSON parsed, "
            "but spreadsheet fields "
            "are missing:"
        )

        for field in sorted(
            missing
        ):
            print(
                f"  - {field}"
            )

        return None

    print("")
    print(
        "[RESPONSE] VALID DEPOP JSON FOUND."
    )
    print("")

    return (
        cleaned,
        data
    )


# =========================================================
# WAIT WHILE SCROLLING
# =========================================================

def wait_with_scroll(
    seconds,
    scroll_every=SCROLL_INTERVAL
):
    """
    Wait while periodically scrolling downward.

    This keeps ChatGPT's newest generated content
    moving toward the visible part of the screen.

    Example:
        wait 10 sec
        scroll down
        wait 10 sec
        scroll down
        etc.
    """

    start = time.time()

    while True:
        elapsed = (
            time.time() - start
        )

        remaining = (
            seconds - elapsed
        )

        if remaining <= 0:
            break

        sleep_time = min(
            scroll_every,
            remaining
        )

        print(
            f"[WAIT] ChatGPT thinking... "
            f"{remaining:.0f}s remaining "
            f"before next response check."
        )

        # Wait first, THEN scroll.
        time.sleep(
            sleep_time
        )

        # If our timer is complete, no need
        # to perform another scroll.
        elapsed = (
            time.time() - start
        )

        if elapsed >= seconds:
            break

        # Move mouse into the ChatGPT conversation area.
        screen_width, screen_height = (
            pyautogui.size()
        )

        pyautogui.moveTo(
            screen_width // 2,
            int(screen_height * 0.70),
            duration=0.20
        )

        print(
            f"[SCROLL] Scrolling down "
            f"{abs(SCROLL_AMOUNT)} units..."
        )

        pyautogui.scroll(
            SCROLL_AMOUNT
        )


# =========================================================
# WAIT FOR VALID CHATGPT RESPONSE
# =========================================================

def wait_for_valid_response():
    print("")
    print(
        f"[RESPONSE] Giving ChatGPT "
        f"{INITIAL_RESPONSE_WAIT}s "
        "before the first check..."
    )

    # Instead of doing one long idle sleep,
    # periodically scroll while ChatGPT thinks.
    wait_with_scroll(
        INITIAL_RESPONSE_WAIT,
        scroll_every=SCROLL_INTERVAL
    )

    start = time.time()

    while True:
        elapsed = (
            time.time() - start
        )

        if (
            elapsed
            > MAX_RESPONSE_WAIT
        ):
            screenshot = (
                save_failure_screenshot(
                    "CHATGPT_RESPONSE_TIMEOUT"
                )
            )

            raise TimeoutError(
                "\nNo valid final JSON was "
                "detected before timeout.\n\n"
                f"Screenshot:\n{screenshot}\n\n"
                f"Last copied attempt:\n"
                f"{DEBUG_COPY_FILE}"
            )

        # Put newest response/footer on screen.
        print(
            "[RESPONSE] Jumping to newest "
            "part of conversation..."
        )

        pyautogui.hotkey(
            "ctrl",
            "end"
        )

        time.sleep(1)

        result = (
            try_copy_valid_response()
        )

        if result is not None:
            response_text, data = (
                result
            )

            print(
                "[RESPONSE] Valid final JSON "
                f"detected after {elapsed:.0f}s."
            )

            return (
                response_text,
                data
            )

        print(
            "[RESPONSE] Still waiting for "
            f"valid JSON... {elapsed:.0f}s"
        )

        # Wait for the next response check,
        # while continuing to scroll downward.
        wait_with_scroll(
            CHECK_INTERVAL,
            scroll_every=SCROLL_INTERVAL
        )


# =========================================================
# PREFLIGHT
# =========================================================

print("")
print(
    "=============================================="
)
print(
    "       DEPOPBOT VISUAL-ANCHOR TRIAL"
)
print(
    "=============================================="
)
print("")

validate_file(
    PROMPT_FILE,
    "master prompt"
)

validate_file(
    RAW_PHOTO_FOLDER,
    "raw photo folder"
)

validate_file(
    BOOKMARKS_FOLDER,
    "Bookmarks anchor"
)

validate_file(
    CHATGPT_BOOKMARK,
    "ChatGPT bookmark anchor"
)

validate_file(
    CHATGPT_TEXTBOX,
    "ChatGPT textbox anchor"
)

validate_file(
    COPY_RESPONSE,
    "ChatGPT Copy-response anchor"
)

master_prompt = (
    PROMPT_FILE.read_text(
        encoding="utf-8"
    )
)

test_photo = (
    find_test_photo()
)

print(
    f"Master prompt loaded: "
    f"{len(master_prompt):,} characters"
)

print(
    f"Test photo: "
    f"{test_photo.name}"
)

print("")
print(
    "Starting in 3 seconds..."
)

print(
    "Move mouse to TOP-LEFT at any time "
    "to emergency-stop."
)

time.sleep(3)


# =========================================================
# STEP 1 — OPEN CHROME THROUGH WINDOWS SEARCH
# =========================================================

print("")
print(
    "STEP 1 — Open Chrome"
)

open_chrome_via_start_menu()


# =========================================================
# STEP 2 — FIND + OPEN BOOKMARKS
# =========================================================

print("")
print(
    "STEP 2 — All Bookmarks"
)

click_anchor(
    BOOKMARKS_FOLDER,
    name="All_Bookmarks",
    confidence=0.82,
    timeout=20,
    pause_after=1
)


# =========================================================
# STEP 3 — FIND + OPEN CHATGPT BOOKMARK
# =========================================================

print("")
print(
    "STEP 3 — ChatGPT bookmark"
)

click_anchor(
    CHATGPT_BOOKMARK,
    name="ChatGPT_Bookmark",
    confidence=0.82,
    timeout=20,
    pause_after=5
)


# =========================================================
# STEP 4 — FIND + CLICK CHATGPT TEXTBOX
# =========================================================

print("")
print(
    "STEP 4 — ChatGPT textbox"
)

click_anchor(
    CHATGPT_TEXTBOX,
    name="ChatGPT_Textbox",
    confidence=0.80,
    timeout=30,
    pause_after=1
)


# =========================================================
# STEP 5 — PASTE MASTER PROMPT
# =========================================================

print("")
print(
    "STEP 5 — Paste master prompt"
)

pyperclip.copy(
    master_prompt
)

pyautogui.hotkey(
    "ctrl",
    "v"
)

time.sleep(5)


# =========================================================
# STEP 6 — PASTE *_001 PHOTO
# =========================================================

print("")
print(
    f"STEP 6 — Paste photo: "
    f"{test_photo.name}"
)

copy_image_to_clipboard(
    test_photo
)

time.sleep(1)

pyautogui.hotkey(
    "ctrl",
    "v"
)

time.sleep(5)


# =========================================================
# STEP 7 — SEND
# =========================================================

print("")
print(
    "STEP 7 — Send prompt + photo"
)

pyautogui.press(
    "enter"
)

time.sleep(3)


# =========================================================
# STEP 8 — WAIT FOR VALID CHATGPT JSON
# =========================================================

print("")
print(
    "STEP 8 — Wait for research + analysis"
)

response_text, data = (
    wait_for_valid_response()
)


# =========================================================
# STEP 9 — SAVE OUTPUT
# =========================================================

RAW_RESPONSE_FILE.write_text(
    response_text,
    encoding="utf-8"
)

JSON_RESPONSE_FILE.write_text(
    json.dumps(
        data,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)


# =========================================================
# STEP 10 — PRINT SPREADSHEET VALUES
# =========================================================

print("")
print(
    "=============================================="
)
print(
    "          VALUES FOR DEPOP SPREADSHEET"
)
print(
    "=============================================="
)
print("")

for field, value in (
    data["csv_fields"].items()
):
    print(
        f"{field}: {value}"
    )


print("")
print(
    "=============================================="
)
print(
    "               MARKET SUMMARY"
)
print(
    "=============================================="
)
print("")

for field, value in (
    data["market_summary"].items()
):
    print(
        f"{field}: {value}"
    )


print("")
print(
    "Needs review:",
    data.get(
        "needs_review",
        []
    )
)


# =========================================================
# SUCCESS
# =========================================================

print("")
print(
    "=============================================="
)
print(
    "                   SUCCESS"
)
print(
    "=============================================="
)
print("")

print(
    "Raw response:"
)
print(
    RAW_RESPONSE_FILE
)

print("")

print(
    "Parsed JSON:"
)
print(
    JSON_RESPONSE_FILE
)

print("")

print(
    "DepopBot visual-anchor trial complete."
)
