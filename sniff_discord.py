import os
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import discord
from discord.ext import tasks, commands
import asyncio
from dotenv import load_dotenv
import logging
import time
import random

load_dotenv()

PRODUCT_URL = "https://www.walmart.com/ip/WD-BLACK-4TB-SN850X-NVMe-Internal-Gaming-SSD-Solid-State-Drive-Gen4-PCIe-M-2-2280-Up-to-7-300-MB-s-WDS400T2X0E/1916728529"
TARGET_PRICE = 149.99
CHECK_INTERVAL = 600 

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PriceChecker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.driver = None
        self.check_counter = 0
        self.setup_driver()
        self.price_check.start()
        
    def setup_driver(self):
        """setup undetected chromedriver in headless mode"""
        try:
            options = uc.ChromeOptions()
            
            # headless
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')
            options.add_argument('--blink-settings=imagesEnabled=false')
            
            # stealth
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-notifications')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--ignore-certificate-errors')
            
            # setting user agent
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            self.driver = uc.Chrome(
                options=options,
                use_subprocess=False, 
                headless=True 
            )
        
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("undetected chromedriver setup successfully in headless mode")
            
        except Exception as e:
            logger.error(f"error setting up chromedriver: {e}")
            self.driver = None
    
    def get_walmart_price(self):
        """get current price using undetected chromedriver"""
        if not self.driver:
            logger.error("chromedriver not available")
            return None
            
        try:
            logger.info("loading product page with undetected chromedriver...")
            
            # randomly delaying before loading
            time.sleep(random.uniform(2, 5))
            
            self.driver.get(PRODUCT_URL)
            
            # wait for webpage load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # more delay to appear more human like
            time.sleep(random.uniform(3, 7))
            
            # price detection
            price_selectors = [
                "span[data-automation-id='product-price']",
                "span.price-characteristic",
                "div[data-testid='price-wrap']",
                "span[itemprop='price']",
                "div.inline-flex span[aria-hidden='true']",
                "span.b.lh-copy.dark-gray.f2.mr1",
                "div[data-testid='list-price']",
                "div[data-testid='price-styling']",
                "div[data-item-id='price']",
                "div.price-display",
                "span[class*='price']",
                "div[class*='price']",
                "span[data-testid='price-currency']",
                "div[data-testid='price-current']",
                "span.price-group",
            ]
            
            for selector in price_selectors:
                try:
                    price_element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    price_text = price_element.text
                    logger.info(f"found price text with selector '{selector}': {price_text}")

                    price_match = re.search(r'(\d+[,.]?\d*[,.]?\d*)', price_text.replace(',', ''))
                    if price_match:
                        price = float(price_match.group(1).replace(',', ''))
                        logger.info(f"extracted price via CSS: ${price}")
                        return price
                except Exception as e:
                    logger.debug(f"selector '{selector}' failed: {e}")
                    continue
            
            logger.info("could not find price using CSS selectors, trying XPath...")
            
            # if css doesn't work, try xpath
            xpath_selectors = [
                "//*[contains(@class, 'price')]",
                "//*[contains(text(), '$')]",
                "//*[@data-automation-id='product-price']",
                "//span[@class='price-characteristic']"
            ]
            
            for xpath in xpath_selectors:
                try:
                    price_element = self.driver.find_element(By.XPATH, xpath)
                    price_text = price_element.text
                    price_match = re.search(r'(\d+[,.]?\d*[,.]?\d*)', price_text.replace(',', ''))
                    if price_match:
                        price = float(price_match.group(1).replace(',', ''))
                        logger.info(f"extracted price via XPath: ${price}")
                        return price
                except:
                    continue
            
            self.driver.save_screenshot('walmart_debug.png')
            logger.info("saved screenshot to walmart_debug.png")
            
            return None
            
        except Exception as e:
            logger.error(f"error getting price: {e}")
            if self.driver:
                self.driver.save_screenshot('walmart_error.png')
                logger.info("saved error screenshot to walmart_error.png")
            return None
    
    def close_driver(self):
        """close the chromedriver instance"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("chromedriver closed")
    
    @tasks.loop(seconds=CHECK_INTERVAL)
    async def price_check(self):
        """check price and send notification if below target"""
        self.check_counter += 1
        
        price = await asyncio.get_event_loop().run_in_executor(None, self.get_walmart_price)
        
        if price is not None:
            logger.info(f"Current price: ${price:.2f} (Check #{self.check_counter})")
            
            # send status update every 10 checks (every 50 minutes)
            if self.check_counter % 10 == 0:
                await self.send_status_update(price)
            
            if price <= TARGET_PRICE:
                await self.send_discord_notification(price)
            else:
                logger.info(f"Price ${price:.2f} is above target ${TARGET_PRICE}")
        else:
            logger.warning("Could not fetch price")
    
    async def send_discord_notification(self, price):
        """send notification to discord channel when price is below target"""
        channel = self.bot.get_channel(CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🎯 Price Alert!",
                description=f"The WD Black 4TB SSD is now below ${TARGET_PRICE}!",
                color=0x00ff00
            )
            embed.add_field(name="Current Price", value=f"${price:.2f}", inline=True)
            embed.add_field(name="Target Price", value=f"${TARGET_PRICE}", inline=True)
            embed.add_field(name="Product Link", value=PRODUCT_URL, inline=False)
            embed.add_field(name="Savings", value=f"${TARGET_PRICE - price:.2f} below target!", inline=False)
            embed.set_footer(text=f"Check #{self.check_counter}")

            await channel.send(
                content=f"@everyone <@234052933606440961>",
                embed=embed
    )
            
            try:
                if os.path.exists('walmart_debug.png'):
                    file = discord.File('walmart_debug.png', filename='debug.png')
                    embed.set_image(url="attachment://debug.png")
                    await channel.send(embed=embed, file=file)
                else:
                    await channel.send(embed=embed)
            except Exception as e:
                await channel.send(embed=embed) 
            
            logger.info("Discord notification sent!")
    
    async def send_status_update(self, price):
        """send periodic status update every 10 checks"""
        channel = self.bot.get_channel(CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="📊 Price Check Status",
                description="Regular price check update",
                color=0x0099ff
            )
            embed.add_field(name="Product URL", value=PRODUCT_URL, inline=False)
            embed.add_field(name="Current Price", value=f"${price:.2f}", inline=True)
            embed.add_field(name="Target Price", value=f"${TARGET_PRICE}", inline=True)
            embed.add_field(name="Check Count", value=f"#{self.check_counter}", inline=True)
            embed.add_field(name="Time Running", value=f"{(self.check_counter * CHECK_INTERVAL) / 60:.1f} minutes", inline=True)
            embed.add_field(name="Status", value="✅ Above target" if price > TARGET_PRICE else "🎯 Below target!", inline=True)
            embed.add_field(name="Next Check", value=f"In {CHECK_INTERVAL/60} minutes", inline=True)
            
            await channel.send(embed=embed)
            logger.info(f"Status update sent (Check #{self.check_counter})")
    
    async def send_startup_message(self):
        """send notification when bot starts"""
        channel = self.bot.get_channel(CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🤖 Price Monitor Started",
                description="The Walmart price monitor is now running!",
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Product", value="WD Black 4TB SN850X NVMe SSD", inline=True)
            embed.add_field(name="Target Price", value=f"${TARGET_PRICE}", inline=True)
            embed.add_field(name="Check Interval", value=f"{CHECK_INTERVAL/60} minutes", inline=True)
            embed.add_field(name="Product URL", value=PRODUCT_URL, inline=False)
            embed.add_field(name="Commands", value="Use `!help` to see available commands", inline=False)
            embed.set_footer(text="Monitoring started")
            
            await channel.send(embed=embed)
            logger.info("Startup message sent")
    
    @commands.command(name='check', help='Manually check the current price')
    async def manual_check(self, ctx):
        """manual price check command"""
        await ctx.send("🔄 Checking current price...")
        
        price = await asyncio.get_event_loop().run_in_executor(None, self.get_walmart_price)
        
        if price is not None:
            embed = discord.Embed(
                title="🛒 Manual Price Check",
                color=0x0099ff
            )
            embed.add_field(name="Current Price", value=f"${price:.2f}", inline=True)
            embed.add_field(name="Target Price", value=f"${TARGET_PRICE}", inline=True)
            embed.add_field(name="Status", value="✅ Above target" if price > TARGET_PRICE else "🎯 Below target!", inline=True)
            embed.add_field(name="Difference", value=f"${abs(price - TARGET_PRICE):.2f} {'above' if price > TARGET_PRICE else 'below'} target", inline=True)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Could not fetch the current price. Check logs for details.")
    
    @commands.command(name='status', help='Show current monitoring status')
    async def show_status(self, ctx):
        """Show current monitoring status"""
        # get current price for status
        price = await asyncio.get_event_loop().run_in_executor(None, self.get_walmart_price)
        
        embed = discord.Embed(
            title="📊 Monitoring Status",
            color=0x0099ff
        )
        
        if price is not None:
            embed.add_field(name="Current Price", value=f"${price:.2f}", inline=True)
            embed.add_field(name="Target Price", value=f"${TARGET_PRICE}", inline=True)
            embed.add_field(name="Price Status", value="✅ Above target" if price > TARGET_PRICE else "🎯 Below target!", inline=True)
        else:
            embed.add_field(name="Price Status", value="❌ Unable to fetch", inline=True)
        
        embed.add_field(name="Total Checks", value=f"#{self.check_counter}", inline=True)
        embed.add_field(name="Check Interval", value=f"{CHECK_INTERVAL/60} minutes", inline=True)
        embed.add_field(name="Time Running", value=f"{(self.check_counter * CHECK_INTERVAL) / 3600:.1f} hours", inline=True)
        embed.add_field(name="Next Auto Check", value=f"In {CHECK_INTERVAL/60} minutes", inline=True)
        embed.add_field(name="Product", value="WD Black 4TB SN850X NVMe SSD", inline=True)
        embed.add_field(name="Monitor Active", value="✅ Yes" if self.price_check.is_running() else "❌ No", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='restart', help='Restart the price monitoring')
    async def restart_monitor(self, ctx):
        """Restart the price monitoring task"""
        self.price_check.restart()
        await ctx.send("✅ Price monitoring has been restarted!")
    
    @commands.command(name='stop', help='Stop the price monitoring')
    async def stop_monitor(self, ctx):
        """Stop the price monitoring task"""
        self.price_check.cancel()
        await ctx.send("⏹️ Price monitoring has been stopped. Use `!restart` to resume.")
    
    @commands.command(name='target', help='Set a new target price')
    async def set_target(self, ctx, new_target: float):
        """Set a new target price"""
        global TARGET_PRICE
        old_target = TARGET_PRICE
        TARGET_PRICE = new_target
        
        embed = discord.Embed(
            title="🎯 Target Price Updated",
            color=0x0099ff
        )
        embed.add_field(name="Old Target", value=f"${old_target:.2f}", inline=True)
        embed.add_field(name="New Target", value=f"${TARGET_PRICE:.2f}", inline=True)
        embed.add_field(name="Changed By", value=ctx.author.display_name, inline=True)
        
        await ctx.send(embed=embed)
        logger.info(f"Target price changed from ${old_target} to ${TARGET_PRICE} by {ctx.author}")

    @commands.command(name='interval', help='Set a new check interval (in seconds)')
    async def set_interval(self, ctx, new_interval: int):
        global CHECK_INTERVAL
        old_interval = CHECK_INTERVAL
        CHECK_INTERVAL = new_interval

        # restart loop with new interval
        self.price_check.change_interval(seconds=CHECK_INTERVAL)

        embed = discord.Embed(
            title="⏰ Check Interval Updated",
            color=0x0099ff
        )
        embed.add_field(name="Old Interval", value=f"{old_interval} sec", inline=True)
        embed.add_field(name="New Interval", value=f"{CHECK_INTERVAL} sec", inline=True)
        embed.add_field(name="Changed By", value=ctx.author.display_name, inline=True)

        await ctx.send(embed=embed)
        logger.info(f"Check interval changed from {old_interval} to {CHECK_INTERVAL} by {ctx.author}")
    
    @price_check.before_loop
    async def before_price_check(self):
        await self.bot.wait_until_ready()
        logger.info("Price checker is ready!")
        # start up message
        await self.send_startup_message()
    
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.price_check.cancel()
        self.close_driver()

# bot start
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has logged in!')
    await bot.add_cog(PriceChecker(bot))

@bot.event
async def on_command_error(ctx, error):
    """handling command errors"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `!help` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument. Check `!help` for command usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument. Please check your input.")
    else:
        await ctx.send("❌ An error occurred while executing the command.")
        logger.error(f"Command error: {error}")

# TEST FUNCTION
def test_price_extraction():
    """test price extraction without starting the bot"""
    print("testing Walmart price extraction with undetected chromedriver...")
    
    try:
        # temp driver for testing
        options = uc.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        driver = uc.Chrome(options=options)
        
        # test price extraction logic
        driver.get(PRODUCT_URL)
        time.sleep(5)  # page load
        
        # price find
        selectors = [
            "span[data-automation-id='product-price']",
            "span.price-characteristic",
            "div[data-testid='price-wrap']"
        ]
        
        for selector in selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                price_text = element.text
                match = re.search(r'(\d+\.?\d*)', price_text.replace(',', ''))
                if match:
                    price = float(match.group(1))
                    print(f"Success! Found price: ${price}")
                    driver.quit()
                    return price
            except:
                continue
        
        driver.save_screenshot('test_debug.png')
        print("could not find price. Screenshot saved to test_debug.png")
        driver.quit()
        return None
        
    except Exception as e:
        print(f"Test error: {e}")
        return None

if __name__ == "__main__":
    if not DISCORD_TOKEN or not CHANNEL_ID:
        print("error: Please set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in .env file")
        exit(1)
    
    # Test price extraction first
    # print("Testing price extraction before starting bot...")
    # test_price = test_price_extraction()
    
    # if test_price is None:
    #     print("Warning: Could not extract price in initial test.")
    #     print("The bot will still run, but check the debug screenshots.")
    # else:
    #     print(f"Test successful! Price: ${test_price}")
    
    print("starting Discord bot...")
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Bot error: {e}")