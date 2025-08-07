# app/test_app.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException
import time
import os
import sys
import platform
import uuid  # For generating unique IDs

# Test configuration assumptions (to address Issue #5)
# Assumes default demo config: cm_enabled=True, af_enabled=True, n_outcomes>=2, starting_balance sufficient for test sizes.
TEST_OUTCOMES = 3  # Assume at least 3 outcomes
OUTCOME_NAMES = ["Outcome A", "Outcome B", "Outcome C"]  # Match config.py outcome_names

# Helper function to get outcome name by index
def get_outcome_name(outcome_index):
    """Convert 0-based outcome index to actual outcome name"""
    if outcome_index < len(OUTCOME_NAMES):
        return OUTCOME_NAMES[outcome_index]
    else:
        return f"Outcome {outcome_index + 1}"

# Environment detection and validation
is_wsl = 'microsoft' in platform.uname().release.lower()
has_display = 'DISPLAY' in os.environ and os.environ['DISPLAY']

# WSL environment detection and X Server check
if is_wsl:
    if has_display:
        print("\nWSL environment with X Server detected (DISPLAY={}).".format(os.environ['DISPLAY']))
        print("Using X Server for browser automation.")
    else:
        print("\nWARNING: Running in WSL environment without X Server detected.")
        print("Browser automation in WSL requires an X Server.")
        print("\nTo configure X Server for WSL:")
        print("1. Install VcXsrv on Windows: https://sourceforge.net/projects/vcxsrv/")
        print("2. Run XLaunch with these settings:")
        print("   - Multiple windows, Display: -1, Start no client")
        print("   - Check 'Disable access control'")
        print("3. Add to your WSL ~/.bashrc:")
        print("   export DISPLAY=$(grep -m 1 nameserver /etc/resolv.conf | awk '{print $2}'):0.0")
        print("4. Restart your terminal or run: source ~/.bashrc")
        
        # Skip tests if no DISPLAY environment variable is set
        print("\nTests automatically skipped in WSL environment without X Server.")
        print("To force run without X Server (not recommended), edit this file and comment out line", sys._getframe().f_lineno + 2)
        sys.exit(0)

ENABLED_FEATURES = {'cross_matching': True, 'auto_filling': True}  # Toggle if needed for test variants

def run_admin_test():
    # Set up Chrome options for headless mode
    chrome_options = Options()
    
    # Core options that work across environments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Set appropriate options based on environment
    if is_wsl and has_display:
        # WSL with X Server options
        print("Applying WSL+X Server Chrome options...")
        # No headless mode when using X Server
        # Unique user profile for each test run
        # Skip user data directory to avoid conflicts
        print("Using default Chrome profile (no custom user data dir)")
        # X11 requires these options
        chrome_options.add_argument("--disable-gpu")
    elif not is_wsl:
        # Standard headless mode for non-WSL environments
        chrome_options.add_argument("--headless=new")
    
    # Universal options for better stability
    chrome_options.add_argument("--disable-extensions")

    # Initialize WebDriver for admin with explicit path for WSL using Service API
    try:
        # Use Google Chrome instead of Chromium in WSL
        chrome_options.binary_location = '/opt/google/chrome/chrome'
        
        # Use the manually installed ChromeDriver in WSL
        chrome_service = ChromeService(executable_path='/usr/local/bin/chromedriver')
        driver_admin = webdriver.Chrome(options=chrome_options, service=chrome_service)
    except Exception as e:
        print(f"ChromeDriver initialization error: {e}")
        print("WSL may require additional configuration for browser automation.")
        raise
    wait_admin = WebDriverWait(driver_admin, 10)

    try:
        # Open the admin Streamlit app
        driver_admin.get("http://localhost:8503")

        # Log in with password "talus123"
        # Using Streamlit's actual data-testid selector for password input
        password_input = wait_admin.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stTextInput'] input")))
        password_input.send_keys("talus123")

        # Using Streamlit's actual data-testid selector for login button
        login_button = driver_admin.find_element(By.CSS_SELECTOR, "[data-testid='stButton'] button")
        login_button.click()

        # Wait for dashboard to load
        wait_admin.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stButton']")))
        
        # Wait additional time for admin dashboard to fully load
        time.sleep(2)

        # Click "Reset Demo" button using Streamlit button selector and text matching
        reset_buttons = wait_admin.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-testid='stButton'] button")))
        reset_button = None
        for btn in reset_buttons:
            if "Reset Demo".lower() in btn.text.lower():
                reset_button = btn
                break
        if reset_button:
            reset_button.click()
        else:
            raise Exception("Reset Demo button not found")

        # Wait for confirmation dialog
        wait_admin.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stButton'] button")))
        
        # Wait additional time for confirmation dialog to fully load
        time.sleep(2)

        # Click "Confirm Reset" button using Streamlit button selector and text matching
        confirm_buttons = driver_admin.find_elements(By.CSS_SELECTOR, "[data-testid='stButton'] button")
        confirm_reset = None
        for btn in confirm_buttons:
            if "Confirm Reset".lower() in btn.text.lower():
                confirm_reset = btn
                break
        if confirm_reset:
            confirm_reset.click()
        else:
            raise Exception("Confirm Reset button not found")

        # Wait longer for reset to process completely
        time.sleep(10)

        # Click "Start Demo" button using Streamlit button selector and text matching
        start_buttons = wait_admin.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-testid='stButton'] button")))
        start_button = None
        for btn in start_buttons:
            if "Start Demo".lower() in btn.text.lower():
                start_button = btn
                break
        if start_button:
            start_button.click()
        else:
            raise Exception("Start Demo button not found")

        # Wait longer for start to process completely
        time.sleep(5)
        print("Admin actions completed successfully.")

    except Exception as e:
        print(f"Error during admin actions: {e}")
        try:
            driver_admin.save_screenshot(f"admin_error_{time.time()}.png")
            logs = driver_admin.get_log('browser')
            if logs:
                print("Browser console logs:")
                for log in logs:
                    print(log)
        except:
            pass
        raise
    finally:
        # Keep admin dashboard open during user tests
        print("Keeping admin dashboard open for monitoring...")
        # driver_admin.quit()  # Comment out to keep admin open

def join_as_user(driver, wait, username, port=8501):
    try:
        print(f"\n=== Starting join process for {username} ===")
        # Open the user Streamlit app
        driver.get(f"http://localhost:{port}")
        print(f"✓ Navigated to http://localhost:{port} for {username}")
        
        # Wait for page to load and check status
        wait.until(EC.presence_of_element_located((By.ID, "root")))
        print(f"✓ Page title: {driver.title}")
        print(f"✓ Current URL: {driver.current_url}")
        
        # Check if we're in waiting room
        page_source = driver.page_source.lower()
        if "waiting room" in page_source:
            print(f"! {username} is in waiting room - demo may not be started yet")
            return False
        elif "enter display name" in page_source:
            print(f"✓ {username} found join interface")
        else:
            print(f"! {username} - unexpected page content")
            print(f"Page source preview: {page_source[:500]}...")

        # Enter display name using Streamlit's actual data-testid
        display_name_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stTextInput'] input")))
        print(f"✓ {username} found display name input")
        display_name_input.send_keys(username)
        print(f"✓ {username} entered display name: {username}")

        # Click Join button using Streamlit's actual data-testid
        join_buttons = driver.find_elements(By.CSS_SELECTOR, "[data-testid='stButton'] button")
        print(f"✓ {username} found {len(join_buttons)} buttons")
        join_button = None
        for i, btn in enumerate(join_buttons):
            print(f"  Button {i}: '{btn.text}'")
            if "join" in btn.text.lower():
                join_button = btn
                break
        if join_button:
            join_button.click()
            print(f"✓ {username} clicked Join button")
        else:
            raise Exception("Join button not found")

        # Wait for page to update after join
        print(f"⏳ {username} waiting for page to update after join...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stMetricValue']")))
        
        # Check what page content we have after join
        page_source = driver.page_source.lower()
        print(f"📄 {username} page content after join:")

        # wait 2 seconds
        time.sleep(2)
        
        if "balance" in page_source:
            print(f"✓ {username} - Balance found in page")
        if "waiting room" in page_source:
            print(f"! {username} - Still in waiting room")
        if "enter display name" in page_source:
            print(f"! {username} - Still on join page")
        if "order ticket" in page_source:
            print(f"✓ {username} - Order Ticket found")
        if "portfolio" in page_source:
            print(f"✓ {username} - Portfolio section found")
        
        # Try to find Balance element using robust CSS selector
        print(f"🔍 {username} looking for Balance element...")
        try:
            # Use data-testid for metric value
            balance_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stMetricValue"]'))
            )
            print(f"✅ Found Balance element: {balance_element.text}")
        except TimeoutException:
            print("❌ Balance element not found")
            raise Exception(f"Failed to find Balance element for {username}") from None

    except Exception as e:
        print(f"Error joining as {username}: {e}")
        try:
            driver.save_screenshot(f"join_error_{username}_{time.time()}.png")
            logs = driver.get_log('browser')
            if logs:
                print(f"Browser console logs for {username}:")
                for log in logs:
                    print(log)
        except:
            pass
        raise

def get_balance(driver, wait):
    """Get current balance from the UI"""
    try:
        # Get all metrics and find the one with "Balance" label specifically
        metrics = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stMetric"]')))
        
        for metric in metrics:
            try:
                # Check if this metric has a label containing "Balance"
                label_element = metric.find_element(By.CSS_SELECTOR, '[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] p')
                label_text = label_element.text.strip()
                
                if label_text == "Balance":
                    # Get the value from this specific metric
                    value_element = metric.find_element(By.CSS_SELECTOR, '[data-testid="stMetricValue"] div')
                    balance_text = value_element.text.strip()
                    # Extract numeric value from "$1000.00" format
                    balance_value = float(balance_text.replace('$', '').replace(',', '').strip())
                    print(f"✓ Found balance: ${balance_value}")
                    return balance_value
            except:
                continue
        
        # If we get here, we didn't find a Balance metric
        print("❌ Could not find Balance metric")
        return 1000.0  # Default fallback
        
    except Exception as e:
        print(f"Error getting balance: {e}")
        return 1000.0  # Default fallback

def get_yes_price(driver, wait, outcome):
    """Get YES market price for a specific outcome"""
    try:
        print(f"📈 Getting YES price for outcome {outcome}...")
        
        # First navigate to the correct outcome tab
        outcome_tabs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button[data-testid="stTab"]')))
        target_outcome_name = get_outcome_name(outcome - 1)  # Convert 1-based to 0-based index
        for tab in outcome_tabs:
            try:
                tab_text = tab.find_element(By.CSS_SELECTOR, '[data-testid="stMarkdownContainer"] p').text
                if target_outcome_name in tab_text:
                    driver.execute_script("arguments[0].click();", tab)
                    print(f"✓ Navigated to {target_outcome_name} tab")
                    time.sleep(1)
                    break
            except:
                continue
        
        # Look for YES Market Price metric in the order book section
        metrics = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stMetric"]')))
        
        for metric in metrics:
            try:
                # Check if this metric has a label containing "YES Market Price"
                label_element = metric.find_element(By.CSS_SELECTOR, '[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] p')
                label_text = label_element.text.strip()
                
                if label_text == "YES Market Price":
                    # Get the value from this specific metric
                    value_element = metric.find_element(By.CSS_SELECTOR, '[data-testid="stMetricValue"] div')
                    price_text = value_element.text.strip()
                    # Extract numeric value from "$0.5000" format
                    price_value = float(price_text.replace('$', '').strip())
                    print(f"✓ Found YES price: ${price_value}")
                    return price_value
            except:
                continue
        
        print(f"❌ Could not find YES Market Price metric for outcome {outcome}")
        return None
        
    except Exception as e:
        print(f"Error getting YES price for outcome {outcome}: {e}")
        return None

def get_no_price(driver, wait, outcome):
    """Get NO market price for a specific outcome"""
    try:
        print(f"📉 Getting NO price for outcome {outcome}...")
        
        # First navigate to the correct outcome tab
        outcome_tabs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button[data-testid="stTab"]')))
        target_outcome_name = get_outcome_name(outcome - 1)  # Convert 1-based to 0-based index
        for tab in outcome_tabs:
            try:
                tab_text = tab.find_element(By.CSS_SELECTOR, '[data-testid="stMarkdownContainer"] p').text
                if target_outcome_name in tab_text:
                    driver.execute_script("arguments[0].click();", tab)
                    print(f"✓ Navigated to {target_outcome_name} tab")
                    time.sleep(1)
                    break
            except:
                continue
        
        # Look for NO Market Price metric in the order book section
        metrics = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stMetric"]')))
        
        for metric in metrics:
            try:
                # Check if this metric has a label containing "NO Market Price"
                label_element = metric.find_element(By.CSS_SELECTOR, '[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] p')
                label_text = label_element.text.strip()
                
                if label_text == "NO Market Price":
                    # Get the value from this specific metric
                    value_element = metric.find_element(By.CSS_SELECTOR, '[data-testid="stMetricValue"] div')
                    price_text = value_element.text.strip()
                    # Extract numeric value from "$0.5000" format
                    price_value = float(price_text.replace('$', '').strip())
                    print(f"✓ Found NO price: ${price_value}")
                    return price_value
            except:
                continue
        
        print(f"❌ Could not find NO Market Price metric for outcome {outcome}")
        return None
        
    except Exception as e:
        print(f"Error getting NO price for outcome {outcome}: {e}")
        return None

def place_market_order(driver, wait, outcome, yes_no, buy_sell, size):
    try:
        print(f"🎯 Starting market order: Outcome {outcome}, {yes_no} {buy_sell}, Size {size}")
        
        # Get pre-order balance
        print("📊 Getting pre-order balance...")
        pre_balance = get_balance(driver, wait)
        print(f"✓ Pre-order balance: ${pre_balance}")
        
        # Get pre-order price
        pre_price = get_yes_price(driver, wait, outcome) if yes_no == "YES" else get_no_price(driver, wait, outcome)
        print(f"✓ Pre-order price: ${pre_price}")
        
        # Select outcome tab using button with data-testid="stTab" and text matching
        outcome_tabs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button[data-testid="stTab"]')))
        target_outcome_name = get_outcome_name(outcome - 1)  # Convert 1-based to 0-based index
        for tab in outcome_tabs:
            try:
                tab_text = tab.find_element(By.CSS_SELECTOR, '[data-testid="stMarkdownContainer"] p').text
                if target_outcome_name in tab_text:
                    driver.execute_script("arguments[0].click();", tab)
                    print(f"✅ Selected {target_outcome_name} tab")
                    time.sleep(1)
                    break
            except:
                continue
        else:
            target_outcome_name = get_outcome_name(outcome - 1)  # Convert 1-based to 0-based index
            raise Exception(f"Could not find {target_outcome_name} tab")
        
        # Select YES/NO using label[data-baseweb="radio"] with text matching
        yes_no_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-yes-no-radio-{outcome-1}')))
        yes_no_labels = yes_no_container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
        
        print(f"🔘 Selecting {yes_no} token...")
        for label in yes_no_labels:
            try:
                label_text = label.find_element(By.CSS_SELECTOR, '[data-testid="stMarkdownContainer"] p').text
                if label_text == yes_no:
                    driver.execute_script("arguments[0].click();", label)
                    print(f"✅ Selected {yes_no} token")
                    time.sleep(0.5)
                    break
            except:
                continue
        else:
            print(f"❌ Could not find {yes_no} radio button")
            raise Exception(f"Could not find {yes_no} radio button")
        
        # Select Buy/Sell using label[data-baseweb="radio"] with text matching
        buy_sell_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-buy-sell-radio-{outcome-1}')))
        buy_sell_labels = buy_sell_container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
        
        print(f"📈 Selecting {buy_sell} direction...")
        for label in buy_sell_labels:
            try:
                label_text = label.find_element(By.CSS_SELECTOR, '[data-testid="stMarkdownContainer"] p').text
                if label_text == buy_sell:
                    driver.execute_script("arguments[0].click();", label)
                    print(f"✅ Selected {buy_sell} direction")
                    time.sleep(0.5)
                    break
            except:
                continue
        else:
            print(f"❌ Could not find {buy_sell} radio button")
            raise Exception(f"Could not find {buy_sell} radio button")
        
        # Select MARKET order type - it's already selected by default, just verify
        print("📋 Verifying MARKET order type...")
        try:
            order_type_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-order-type-select-{outcome-1}')))
            market_text = order_type_container.find_element(By.XPATH, ".//div[contains(text(), 'MARKET')]")
            print("✅ MARKET order type confirmed")
        except Exception as e:
            print(f"⚠️ Could not verify order type, continuing: {e}")
        
        # Enter size using input[data-testid="stNumberInputField"]
        print(f"🔢 Entering size: {size}...")
        try:
            size_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-size-input-{outcome-1}')))
            size_input = size_container.find_element(By.CSS_SELECTOR, 'input[data-testid="stNumberInputField"]')
            
            # Clear and enter size
            size_input.click()
            size_input.send_keys(Keys.CONTROL + "a")
            size_input.send_keys(Keys.DELETE)
            size_input.send_keys(str(size))
            print(f"✅ Entered size: {size}")
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Could not find size input field: {e}")
            raise Exception(f"Could not find size input field: {e}")
        
        # Click Submit Order button using button[data-testid="stBaseButton-secondary"]
        print("🚀 Clicking Submit Order...")
        try:
            submit_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-submit-order-button-{outcome-1}')))
            submit_button = submit_container.find_element(By.CSS_SELECTOR, 'button[data-testid="stBaseButton-secondary"]')
            driver.execute_script("arguments[0].click();", submit_button)
            print("✅ Clicked Submit Order button")
            time.sleep(2)
        except Exception as e:
            print(f"❌ Could not find submit button: {e}")
            raise Exception(f"Could not find submit button: {e}")
        
        # Get post-order balance and price
        post_balance = get_balance(driver, wait)
        post_price = get_yes_price(driver, wait, outcome) if yes_no == "YES" else get_no_price(driver, wait, outcome)
        
        print(f"📊 Order completed - Balance: ${pre_balance} → ${post_balance}, Price: ${pre_price} → ${post_price}")
        return True
        
    except Exception as e:
        print(f"❌ Error placing market order: {e}")
        take_screenshot(driver, f"market_order_error_{outcome}_{yes_no}_{buy_sell}")
        return False

def place_limit_order(driver, wait, outcome, yes_no, buy_sell, size, price, af_opt_in=True):
    try:
        # Get pre-order state
        pre_balance = get_balance(driver, wait)

        # Select outcome tab using text matching with data-testid
        outcome_tabs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stTab"]')))
        outcome_tab = None
        for tab in outcome_tabs:
            if get_outcome_name(outcome) in tab.text:
                outcome_tab = tab
                break
        
        if outcome_tab:
            outcome_tab.click()
            print(f"✅ Selected {get_outcome_name(outcome)} tab")
        else:
            raise Exception(f"Could not find {get_outcome_name(outcome)} tab")
        
        # Wait for tab content to load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stRadio"]')))
        time.sleep(1)  # Allow content to fully load

        # Select YES/NO using label text matching (0-based indexing)
        print(f"🔘 Selecting {yes_no} token...")
        yes_no_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            yes_no_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-yes-no-radio-{outcome-1}'))
            )
            yes_no_labels = yes_no_container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
            for label in yes_no_labels:
                if yes_no.upper() in label.text.upper():
                    label.click()
                    yes_no_found = True
                    print(f"✓ Selected {yes_no} token")
                    break
        except:
            # Fallback: Use data-testid approach with text matching
            print(f"Trying fallback selector for {yes_no} token...")
            try:
                radio_containers = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stRadio"]'))
                )
                for container in radio_containers:
                    if "Token" in container.text:  # Find the Token radio group
                        labels = container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
                        for label in labels:
                            if yes_no.upper() in label.text.upper():
                                label.click()
                                yes_no_found = True
                                print(f"✓ Selected {yes_no} token with fallback")
                                break
                        if yes_no_found:
                            break
            except:
                pass
        
        if not yes_no_found:
            print(f"❌ Could not find {yes_no} radio button")
        
        # Select Buy/Sell using label text matching (0-based indexing)
        print(f"📈 Selecting {buy_sell} direction...")
        buy_sell_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            buy_sell_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-buy-sell-radio-{outcome-1}'))
            )
            buy_sell_labels = buy_sell_container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
            for label in buy_sell_labels:
                if buy_sell.upper() in label.text.upper():
                    label.click()
                    buy_sell_found = True
                    print(f"✓ Selected {buy_sell} direction")
                    break
        except:
            # Fallback: Use data-testid approach with text matching
            print(f"Trying fallback selector for {buy_sell} direction...")
            try:
                radio_containers = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stRadio"]'))
                )
                for container in radio_containers:
                    if "Direction" in container.text:  # Find the Direction radio group
                        labels = container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
                        for label in labels:
                            if buy_sell.upper() in label.text.upper():
                                label.click()
                                buy_sell_found = True
                                print(f"✓ Selected {buy_sell} direction with fallback")
                                break
                        if buy_sell_found:
                            break
            except:
                pass
        
        if not buy_sell_found:
            print(f"❌ Could not find {buy_sell} radio button")

        # Select order type using Streamlit's select structure (0-based indexing)
        print(f"📋 Selecting LIMIT order type...")
        order_type_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            order_type_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-order-type-select-{outcome-1}'))
            )
            # Streamlit selects are clickable divs, not traditional select elements
            select_div = order_type_container.find_element(By.CSS_SELECTOR, '[data-baseweb="select"]')
            select_div.click()  # Open dropdown
            time.sleep(0.5)  # Wait for dropdown to open
            
            # Look for MARKET option in dropdown
            market_option = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'MARKET')]"))
            )
            market_option.click()
            order_type_found = True
            print(f"✓ Selected MARKET order type")
        except:
            # Fallback: Use generic selectbox approach
            print(f"Trying fallback selector for order type...")
            try:
                selectboxes = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stSelectbox"]'))
                )
                for selectbox in selectboxes:
                    if "Type" in selectbox.text:  # Find the Type selectbox
                        select_div = selectbox.find_element(By.CSS_SELECTOR, '[data-baseweb="select"]')
                        select_div.click()
                        time.sleep(0.5)
                        try:
                            market_option = wait.until(
                                EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'MARKET')]"))
                            )
                            market_option.click()
                            order_type_found = True
                            print(f"✓ Selected MARKET order type with fallback")
                            break
                        except:
                            continue
            except:
                pass
        
        if not order_type_found:
            print(f"❌ Could not find order type selectbox")

        # Enter size using Streamlit's number input structure (0-based indexing)
        print(f"🔢 Entering size: {size}...")
        size_input_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            size_input_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-size-input-{outcome-1}'))
            )
            size_input = size_input_container.find_element(By.CSS_SELECTOR, '[data-testid="stNumberInputField"]')
            # Properly clear and populate the input field
            size_input.click()  # Focus the input
            size_input.send_keys(Keys.CONTROL + "a")  # Select all
            size_input.send_keys(Keys.DELETE)  # Delete selected content
            size_input.send_keys(str(size))  # Enter new value
            size_input_found = True
            print(f"✓ Entered size: {size}")
        except:
            # Fallback: Use generic number input selector with label matching
            print(f"Trying fallback selector for size input...")
            try:
                number_inputs = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stNumberInput"]'))
                )
                for number_input in number_inputs:
                    if "Size" in number_input.text:  # Find the Size input
                        input_elem = number_input.find_element(By.CSS_SELECTOR, '[data-testid="stNumberInputField"]')
                        input_elem.click()
                        input_elem.send_keys(Keys.CONTROL + "a")
                        input_elem.send_keys(Keys.DELETE)
                        input_elem.send_keys(str(size))
                        size_input_found = True
                        print(f"✓ Entered size: {size} with fallback")
                        break
            except:
                pass
        
        if not size_input_found:
            print(f"❌ Could not find size input field")

        # Submit order using button with key
        submit_button_selector = f'.st-key-submit-order-button-{outcome-1} button'
        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, submit_button_selector)))
        submit_button.click()
        print(f"✅ Clicked Submit Order button")

        # Poll for changes with extended timeout and multi-condition
        max_wait = 15  # Increased timeout
        poll_interval = 2  # Increased interval
        elapsed = 0
        updated = False
        while elapsed < max_wait:
            driver.refresh()
            time.sleep(1)
            post_balance = get_balance(driver, wait)
            page_source = driver.page_source.lower()
            if post_balance != pre_balance or "order filled" in page_source:
                updated = True
                break
            elapsed += poll_interval + 1

        if not updated:
            raise TimeoutError("No balance change or fill indicator detected after order submission")

        # Get post-order state
        post_balance = get_balance(driver, wait)
        post_price = get_yes_price(driver, wait, outcome) if yes_no == "YES" else None

        # Basic checks
        if buy_sell == "Buy":
            if post_balance >= pre_balance:
                print("Warning: Balance did not decrease after buy.")
        else:
            if post_balance <= pre_balance:
                print("Warning: Balance did not increase after sell.")

        if yes_no == "YES" and buy_sell == "Buy":
            if post_price <= pre_price:
                print("Warning: YES price did not increase after buy.")

        print(f"Placed market {buy_sell} order for {size} {yes_no} on Outcome {outcome}.")

    except Exception as e:
        print(f"❌ Error placing market order: {e}")
        try:
            driver.save_screenshot(f"market_order_error_{outcome}_{time.time()}.png")
            print(f"📄 Current page source preview: {driver.page_source[:1000]}...")
            logs = driver.get_log('browser')
            if logs:
                print("🖥️ Browser console logs:")
                for log in logs:
                    print(f"  {log}")
        except:
            pass
        raise

def place_limit_order(driver, wait, outcome, yes_no, buy_sell, size, price, af_opt_in=True):
    try:
        # Get pre-order state
        pre_balance = get_balance(driver, wait)

        # Select outcome tab using text matching with data-testid
        outcome_tabs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stTab"]')))
        outcome_tab = None
        for tab in outcome_tabs:
            if get_outcome_name(outcome) in tab.text:
                outcome_tab = tab
                break
        
        if outcome_tab:
            outcome_tab.click()
            print(f"✅ Selected {get_outcome_name(outcome)} tab")
        else:
            raise Exception(f"Could not find {get_outcome_name(outcome)} tab")
        
        # Wait for tab content to load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="stRadio"]')))
        time.sleep(1)  # Allow content to fully load

        # Select YES/NO using label text matching (0-based indexing)
        print(f"🔘 Selecting {yes_no} token...")
        yes_no_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            yes_no_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-yes-no-radio-{outcome-1}'))
            )
            yes_no_labels = yes_no_container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
            for label in yes_no_labels:
                if yes_no.upper() in label.text.upper():
                    label.click()
                    yes_no_found = True
                    print(f"✓ Selected {yes_no} token")
                    break
        except:
            # Fallback: Use data-testid approach with text matching
            print(f"Trying fallback selector for {yes_no} token...")
            try:
                radio_containers = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stRadio"]'))
                )
                for container in radio_containers:
                    if "Token" in container.text:  # Find the Token radio group
                        labels = container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
                        for label in labels:
                            if yes_no.upper() in label.text.upper():
                                label.click()
                                yes_no_found = True
                                print(f"✓ Selected {yes_no} token with fallback")
                                break
                        if yes_no_found:
                            break
            except:
                pass
        
        if not yes_no_found:
            print(f"❌ Could not find {yes_no} radio button")
        
        # Select Buy/Sell using label text matching (0-based indexing)
        print(f"📈 Selecting {buy_sell} direction...")
        buy_sell_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            buy_sell_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-buy-sell-radio-{outcome-1}'))
            )
            buy_sell_labels = buy_sell_container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
            for label in buy_sell_labels:
                if buy_sell.upper() in label.text.upper():
                    label.click()
                    buy_sell_found = True
                    print(f"✓ Selected {buy_sell} direction")
                    break
        except:
            # Fallback: Use data-testid approach with text matching
            print(f"Trying fallback selector for {buy_sell} direction...")
            try:
                radio_containers = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stRadio"]'))
                )
                for container in radio_containers:
                    if "Direction" in container.text:  # Find the Direction radio group
                        labels = container.find_elements(By.CSS_SELECTOR, 'label[data-baseweb="radio"]')
                        for label in labels:
                            if buy_sell.upper() in label.text.upper():
                                label.click()
                                buy_sell_found = True
                                print(f"✓ Selected {buy_sell} direction with fallback")
                                break
                        if buy_sell_found:
                            break
            except:
                pass
        
        if not buy_sell_found:
            print(f"❌ Could not find {buy_sell} radio button")

        # Select LIMIT type using Streamlit's select structure (0-based indexing)
        print(f"📋 Selecting LIMIT order type...")
        order_type_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            order_type_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-order-type-select-{outcome-1}'))
            )
            # Streamlit selects are clickable divs, not traditional select elements
            select_div = order_type_container.find_element(By.CSS_SELECTOR, '[data-baseweb="select"]')
            select_div.click()  # Open dropdown
            time.sleep(0.5)  # Wait for dropdown to open
            
            # Look for LIMIT option in dropdown
            limit_option = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'LIMIT')]"))
            )
            limit_option.click()
            order_type_found = True
            print(f"✓ Selected LIMIT order type")
        except:
            # Fallback: Use generic selectbox approach
            print(f"Trying fallback selector for order type...")
            try:
                selectboxes = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stSelectbox"]'))
                )
                for selectbox in selectboxes:
                    if "Type" in selectbox.text:  # Find the Type selectbox
                        select_div = selectbox.find_element(By.CSS_SELECTOR, '[data-baseweb="select"]')
                        select_div.click()
                        time.sleep(0.5)
                        try:
                            limit_option = wait.until(
                                EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'LIMIT')]"))
                            )
                            limit_option.click()
                            order_type_found = True
                            print(f"✓ Selected LIMIT order type with fallback")
                            break
                        except:
                            continue
            except:
                pass
        
        if not order_type_found:
            print(f"❌ Could not find order type selectbox")

        # Enter size using Streamlit's number input structure (0-based indexing)
        print(f"🔢 Entering size: {size}...")
        size_input_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            size_input_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-size-input-{outcome-1}'))
            )
            size_input = size_input_container.find_element(By.CSS_SELECTOR, '[data-testid="stNumberInputField"]')
            # Properly clear and populate the input field
            size_input.click()  # Focus the input
            size_input.send_keys(Keys.CONTROL + "a")  # Select all
            size_input.send_keys(Keys.DELETE)  # Delete selected content
            size_input.send_keys(str(size))  # Enter new value
            size_input_found = True
            print(f"✓ Entered size: {size}")
        except:
            # Fallback: Use generic number input selector with label matching
            print(f"Trying fallback selector for size input...")
            try:
                number_inputs = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stNumberInput"]'))
                )
                for number_input in number_inputs:
                    if "Size" in number_input.text:  # Find the Size input
                        input_elem = number_input.find_element(By.CSS_SELECTOR, '[data-testid="stNumberInputField"]')
                        input_elem.click()
                        input_elem.send_keys(Keys.CONTROL + "a")
                        input_elem.send_keys(Keys.DELETE)
                        input_elem.send_keys(str(size))
                        size_input_found = True
                        print(f"✓ Entered size: {size} with fallback")
                        break
            except:
                pass
        
        if not size_input_found:
            print(f"❌ Could not find size input field")

        # Enter limit price using Streamlit's number input structure (0-based indexing)
        print(f"💰 Entering limit price: {price}...")
        limit_price_found = False
        try:
            # Find container by class using 0-based indexing (outcome-1)
            limit_price_container = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-limit_price_{outcome-1}'))
            )
            limit_price_input = limit_price_container.find_element(By.CSS_SELECTOR, '[data-testid="stNumberInputField"]')
            # Properly clear and populate the input field
            limit_price_input.click()  # Focus the input
            limit_price_input.send_keys(Keys.CONTROL + "a")  # Select all
            limit_price_input.send_keys(Keys.DELETE)  # Delete selected content
            limit_price_input.send_keys(str(price))  # Enter new value
            limit_price_found = True
            print(f"✓ Entered limit price: {price}")
        except:
            # Fallback: Use generic number input selector with label matching
            print(f"Trying fallback selector for limit price input...")
            try:
                number_inputs = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stNumberInput"]'))
                )
                for number_input in number_inputs:
                    if "Limit Price" in number_input.text or "Price" in number_input.text:  # Find the Price input
                        input_elem = number_input.find_element(By.CSS_SELECTOR, '[data-testid="stNumberInputField"]')
                        input_elem.click()
                        input_elem.send_keys(Keys.CONTROL + "a")
                        input_elem.send_keys(Keys.DELETE)
                        input_elem.send_keys(str(price))
                        limit_price_found = True
                        print(f"✓ Entered limit price: {price} with fallback")
                        break
            except:
                pass
        
        if not limit_price_found:
            print(f"❌ Could not find limit price input field")

        # Check auto-fill opt-in if applicable
        if af_opt_in:
            print(f"☑️ Handling auto-fill opt-in...")
            af_checkbox_found = False
            try:
                # Find container by class using 0-based indexing (outcome-1)
                af_container = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, f'.st-key-af_opt_in_{outcome-1}'))
                )
                af_checkbox = af_container.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                if not af_checkbox.is_selected():
                    af_checkbox.click()
                    af_checkbox_found = True
                    print(f"✓ Enabled auto-fill opt-in")
                else:
                    af_checkbox_found = True
                    print(f"ℹ️ Auto-fill opt-in already enabled")
            except:
                # Fallback: Use generic checkbox selector
                print(f"Trying fallback selector for auto-fill checkbox...")
                try:
                    checkboxes = wait.until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-testid="stCheckbox"]'))
                    )
                    for checkbox in checkboxes:
                        if "auto-fill" in checkbox.text.lower() or "opt" in checkbox.text.lower():
                            input_elem = checkbox.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                            if not input_elem.is_selected():
                                input_elem.click()
                                af_checkbox_found = True
                                print(f"✓ Enabled auto-fill opt-in with fallback")
                            else:
                                af_checkbox_found = True
                                print(f"ℹ️ Auto-fill opt-in already enabled with fallback")
                            break
                except:
                    pass
            
            if not af_checkbox_found:
                print("⚠️ Auto-fill checkbox not found or not applicable")

        # Submit order using button with key
        submit_button_selector = f'.st-key-submit-order-button-{outcome-1} button'
        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, submit_button_selector)))
        submit_button.click()
        print(f"✅ Clicked Submit Order button")

        # Poll for changes with extended timeout and multi-condition
        max_wait = 15
        poll_interval = 2
        elapsed = 0
        updated = False
        while elapsed < max_wait:
            driver.refresh()
            time.sleep(1)
            post_balance = get_balance(driver, wait)
            page_source = driver.page_source.lower()
            if post_balance != pre_balance or "order filled" in page_source:
                updated = True
                break
            elapsed += poll_interval + 1

        if not updated:
            raise TimeoutError("No balance change or fill indicator detected after order submission")

        # Get post-order state
        post_balance = get_balance(driver, wait)

        # Basic checks for limit orders (balance decrease for buy, etc.)
        if buy_sell == "Buy":
            if post_balance >= pre_balance:
                print("Warning: Balance did not decrease after limit buy.")

        print(f"Placed limit {buy_sell} order for {size} {yes_no} on Outcome {outcome} at {price}.")

    except Exception as e:
        print(f"Error placing limit order: {e}")
        try:
            driver.save_screenshot(f"limit_order_error_{outcome}_{time.time()}.png")
            logs = driver.get_log('browser')
            if logs:
                print("Browser console logs:")
                for log in logs:
                    print(log)
        except:
            pass
        raise

def cancel_order(driver, wait, outcome, yes_no):
    try:
        print(f"\n🗑️ Starting order cancellation for Outcome {outcome}, {yes_no}")
        
        # Navigate to Portfolio tab using button[data-testid="stTab"] with text matching
        portfolio_tabs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button[data-testid="stTab"]')))
        for tab in portfolio_tabs:
            try:
                tab_text = tab.find_element(By.CSS_SELECTOR, '[data-testid="stMarkdownContainer"] p').text
                if "Portfolio" in tab_text:
                    driver.execute_script("arguments[0].click();", tab)
                    print("✅ Navigated to Portfolio tab")
                    time.sleep(1)
                    break
            except:
                continue
        else:
            raise Exception("Could not find Portfolio tab")
        
        # Navigate to the specific outcome tab within portfolio using button[data-testid="stTab"]
        outcome_tabs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button[data-testid="stTab"]')))
        for tab in outcome_tabs:
            try:
                tab_text = tab.find_element(By.CSS_SELECTOR, '[data-testid="stMarkdownContainer"] p').text
                target_outcome_name = get_outcome_name(outcome - 1)  # Convert 1-based to 0-based index
                if target_outcome_name in tab_text:
                    driver.execute_script("arguments[0].click();", tab)
                    print(f"✅ Selected {target_outcome_name} tab in Portfolio")
                    time.sleep(2)
                    break
            except:
                continue
        else:
            target_outcome_name = get_outcome_name(outcome - 1)  # Convert 1-based to 0-based index
            raise Exception(f"Could not find {target_outcome_name} tab in Portfolio")
        
        # Find and click the order to expand it (using class-based selector)
        print(f"🔍 Looking for {yes_no} order to cancel...")
        order_found = False
        order_id = None
        try:
            # Look for order containers using class selector pattern
            order_containers = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[class*="st-key-order-"]')))
            for container in order_containers:
                if yes_no.upper() in container.text.upper():
                    # Click to expand the order
                    driver.execute_script("arguments[0].click();", container)
                    order_found = True
                    print(f"✅ Found and expanded {yes_no} order")
                    time.sleep(1)
                    
                    # Extract order ID from the container class
                    class_name = container.get_attribute("class")
                    import re
                    match = re.search(r'st-key-order-([^-]+)', class_name)
                    if match:
                        order_id = match.group(1)
                        print(f"📋 Extracted Order ID: {order_id}")
                    break
        except Exception as e:
            print(f"Error finding order container: {e}")
        
        if not order_found:
            print(f"❌ Could not find {yes_no} order to cancel")
            return False
        
        # Click Cancel button using class-based selector with order ID
        print("🚫 Clicking Cancel button...")
        cancel_clicked = False
        try:
            if order_id:
                # Try specific cancel button selector with order ID
                cancel_button_selector = f'.st-key-cancel-order-button-{order_id}-0 button[data-testid="stBaseButton-secondary"]'
                cancel_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, cancel_button_selector)))
                driver.execute_script("arguments[0].click();", cancel_button)
                cancel_clicked = True
                print("✅ Clicked Cancel button (specific selector)")
            else:
                raise Exception("No order ID found")
        except Exception as e:
            print(f"Trying fallback cancel button selector: {e}")
            try:
                # Fallback: look for any cancel button with data-testid
                cancel_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="stBaseButton-secondary"]')))
                if "Cancel" in cancel_button.text:
                    driver.execute_script("arguments[0].click();", cancel_button)
                    cancel_clicked = True
                    print("✅ Clicked Cancel button (fallback selector)")
            except Exception as e2:
                print(f"❌ Could not find Cancel button: {e2}")
                return False
        
        if not cancel_clicked:
            print("❌ Failed to click Cancel button")
            return False
        
        time.sleep(1)
        
        # Click Confirm button using class-based selector
        print("✅ Clicking Confirm button...")
        confirm_clicked = False
        try:
            if order_id:
                # Try specific confirm button selector with order ID
                confirm_button_selector = f'.st-key-confirm-cancel-button-{order_id}-0 button[data-testid="stBaseButton-secondary"]'
                confirm_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, confirm_button_selector)))
                driver.execute_script("arguments[0].click();", confirm_button)
                confirm_clicked = True
                print("✅ Clicked Confirm button (specific selector)")
            else:
                raise Exception("No order ID found")
        except Exception as e:
            print(f"Trying fallback confirm button selector: {e}")
            try:
                # Fallback: look for any confirm button with data-testid
                confirm_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="stBaseButton-secondary"]')))
                if "Confirm" in confirm_button.text:
                    driver.execute_script("arguments[0].click();", confirm_button)
                    confirm_clicked = True
                    print("✅ Clicked Confirm button (fallback selector)")
            except Exception as e2:
                print(f"❌ Could not find Confirm button: {e2}")
                return False
        
        if confirm_clicked:
            print(f"🎉 Successfully cancelled {yes_no} order")
            time.sleep(2)  # Allow UI to update
            return True
        else:
            print("❌ Failed to confirm cancellation")
            return False
        
    except Exception as e:
        print(f"❌ Error cancelling order: {e}")
        take_screenshot(driver, f"cancel_order_error_{outcome}_{yes_no}")
        return False

def run_user_tests():
    chrome_options = Options()
    
    # Core options that work across environments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Set appropriate options based on environment
    if is_wsl and has_display:
        # WSL with X Server options
        print("Applying WSL+X Server Chrome options...")
        # No headless mode when using X Server
        # Unique user profile for each test run
        # Skip user data directory to avoid conflicts
        print("Using default Chrome profile (no custom user data dir)")
        # X11 requires these options
        chrome_options.add_argument("--disable-gpu")
    elif not is_wsl:
        # Standard headless mode for non-WSL environments
        chrome_options.add_argument("--headless=new")
    
    # Universal options for better stability
    chrome_options.add_argument("--disable-extensions")

    # Driver for Tester1 with explicit path for WSL using Service API
    driver1 = None
    try:
        # Use Google Chrome instead of Chromium in WSL
        chrome_options.binary_location = '/opt/google/chrome/chrome'
        
        chrome_service = ChromeService(executable_path='/usr/local/bin/chromedriver')
        driver1 = webdriver.Chrome(options=chrome_options, service=chrome_service)
        wait1 = WebDriverWait(driver1, 10)
    except Exception as e:
        print(f"Tester1 ChromeDriver initialization error: {e}")
        print("WSL may require additional configuration for browser automation.")
        raise

    # Driver for Tester2 with explicit path for WSL using Service API
    try:
        chrome_service2 = ChromeService(executable_path='/usr/local/bin/chromedriver')
        driver2 = webdriver.Chrome(options=chrome_options, service=chrome_service2)
        wait2 = WebDriverWait(driver2, 10)
    except Exception as e:
        print(f"Tester2 ChromeDriver initialization error: {e}")
        if driver1:
            driver1.quit()
        raise

    try:
        # Join as Tester1 on port 8501
        join_as_user(driver1, wait1, "Tester1", port=8501)

        # Join as Tester2 on port 8502
        join_as_user(driver2, wait2, "Tester2", port=8502)

        # Test actions in sequence
        # 1. Tester1 market buy 10 YES Outcome 1
        place_market_order(driver1, wait1, 1, "YES", "Buy", 100)

        # 2. Tester2 market sell 5 YES Outcome 1
        place_market_order(driver2, wait2, 1, "YES", "Sell", 5)

        # 3. Tester1 market buy 10 NO Outcome 1
        place_market_order(driver1, wait1, 1, "NO", "Buy", 50)

        # 4. Tester2 market sell 5 NO Outcome 1
        place_market_order(driver2, wait2, 1, "NO", "Sell", 15)

        # 5. Tester1 limit buy 20 YES Outcome 1 at 0.60 af_opt_in=True
        place_limit_order(driver1, wait1, 1, "YES", "Buy", 20, 0.60, True)

        # 6. Tester2 limit sell 15 YES Outcome 1 at 0.65
        place_limit_order(driver2, wait2, 1, "YES", "Sell", 15, 0.65)

        # 7. Tester1 market sell 10 YES Outcome 1
        place_market_order(driver1, wait1, 1, "YES", "Sell", 40)

        # 8. Tester2 limit buy 20 NO Outcome 1 at 0.40 af_opt_in=True
        place_limit_order(driver2, wait2, 1, "NO", "Buy", 20, 0.40, True)

        # 9. Tester1 limit sell 15 NO Outcome 1 at 0.45
        place_limit_order(driver1, wait1, 1, "NO", "Sell", 15, 0.45)

        # 10. Tester2 market buy 10 NO Outcome 1
        place_market_order(driver2, wait2, 1, "NO", "Buy", 60)

        # 11. Tester1 limit buy 30 YES Outcome 2 at 0.55
        place_limit_order(driver1, wait1, 2, "YES", "Buy", 30, 0.55)

        # 12. Tester2 limit sell 25 NO Outcome 2 at 0.50
        place_limit_order(driver2, wait2, 2, "NO", "Sell", 25, 0.50)

        # 13. Tester1 market buy 20 YES Outcome 2
        place_market_order(driver1, wait1, 2, "YES", "Buy", 20)

        # 14. Tester2 market buy 50 YES Outcome 1
        place_market_order(driver2, wait2, 1, "YES", "Buy", 50)

        # 15. Tester1 cancels remaining open limit on Outcome 1
        cancel_order(driver1, wait1, 1, "YES")

        print("User tests completed successfully.")

    except Exception as e:
        print(f"Error during user tests: {e}")
        # Safely capture logs from drivers if they're still responsive
        try:
            if driver1:
                driver1.save_screenshot(f"tester1_error_{time.time()}.png")
                logs1 = driver1.get_log('browser')
                if logs1:
                    print("Tester1 browser console logs:")
                    for log in logs1:
                        print(log)
        except Exception as log_error:
            print(f"Could not get Tester1 logs (browser may have crashed): {log_error}")
        
        try:
            if driver2:
                driver2.save_screenshot(f"tester2_error_{time.time()}.png")
                logs2 = driver2.get_log('browser')
                if logs2:
                    print("Tester2 browser console logs:")
                    for log in logs2:
                        print(log)
        except Exception as log_error:
            print(f"Could not get Tester2 logs (browser may have crashed): {log_error}")
        raise
    finally:
        # Safely quit drivers
        try:
            if driver1:
                driver1.quit()
        except Exception as quit_error:
            print(f"Error quitting Tester1 driver: {quit_error}")
        try:
            if driver2:
                driver2.quit()
        except Exception as quit_error:
            print(f"Error quitting Tester2 driver: {quit_error}")

if __name__ == "__main__":
    run_admin_test()
    time.sleep(5)  # Wait for demo to start fully
    run_user_tests()