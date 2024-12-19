from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory, current_app, send_file, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from sqlalchemy import create_engine, text, inspect, delete
from sqlalchemy.orm import scoped_session, sessionmaker
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers import SchedulerAlreadyRunningError
from apscheduler.schedulers.base import SchedulerNotRunningError
from datetime import datetime, timedelta, timezone
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import BadRequest
from bcrypt import gensalt, hashpw
from dotenv import load_dotenv
from apscheduler.jobstores.base import JobLookupError
import redis
import os
import random
import bcrypt
import jwt
from functools import wraps

import secrets

load_dotenv()

client_build_path = os.path.join(os.path.dirname(__file__), '../client/build')

app = Flask(__name__, static_folder=client_build_path, template_folder='templates')

CORS(app, supports_credentials=True, resources={r"/*": {"origins": os.getenv('ALLOWED_ORIGINS', '*').split(',')}})

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_jwt_secret_key')

game_password_hashed = generate_password_hash('game_password')

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

# Use environment variables for sensitive data

db_path = os.environ.get('DATABASE_URL', 'sqlite:///stock_exchange_game.db')
if db_path.startswith("postgres://"):
    db_path = db_path.replace("postgres://", "postgresql://", 1)  # Heroku fix for SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = db_path

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_COOKIE_NAME'] = 'session'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_KEY_PREFIX'] = 'flask-session:'
app.config['SESSION_REDIS'] = redis.StrictRedis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'True') == 'True'
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to cookies
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=240)  # or whatever is appropriate

# Initialize the database
db = SQLAlchemy(app)

# Set the SQLAlchemy instance to store session data
app.config['SESSION_SQLALCHEMY'] = db

# Initialize the session with the FlaskSession object
Session(app)

# Initialize the scheduler
scheduler = BackgroundScheduler()
scheduler_running = False  # New flag to track if the scheduler is running
scheduler_shutting_down = False  # Define and initialize the variable
scheduler.add_jobstore('sqlalchemy', url=app.config['SQLALCHEMY_DATABASE_URI'])

# Global Flags for New Features
supply_demand_enabled = True  # Toggle for supply-demand mechanics
ai_players_enabled = True  # Toggle for AI players

# AI Player Names and Strategies
AI_PLAYER_NAMES = ["Bot 1", "Bot 2", "Bot 3", "Bot 4", "Bot 5"]

# Constants for Market Cap Scaling
DEFAULT_MARKET_CAP = 1_000  # Default market capitalization value for all stocks
MARKET_CAP_SCALING_FACTOR = 0.0001  # Percentage scaling for market cap effects on supply-demand


# Add this back for direct SQLAlchemy session management
DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///stock_exchange_game.db')
engine = create_engine(DATABASE_URI)
session_factory = sessionmaker(bind=engine)
RawSQLSession = scoped_session(session_factory)  # Renamed to avoid conflict with Flask sessions

def generate_jwt_token(player_id):
    payload = {
        'exp': datetime.now(timezone.utc) + timedelta(hours=24),  # Token expiration time
        'iat': datetime.now(timezone.utc),  # Issued at time
        'sub': player_id  # Subject (player_id)
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def decode_jwt_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['sub']
    except jwt.ExpiredSignatureError:
        return None  # Token expired
    except jwt.InvalidTokenError:
        return None  # Invalid token

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split()[1]

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = db.session.query(Player).filter_by(player_id=data['player_id']).first()
        except:
            return jsonify({'message': 'Token is invalid!'}), 401

        return f(current_user, *args, **kwargs)
    
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('admin_logged_in') is not True:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def set_csp_header(response):
    csp = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; frame-src 'none';"
    response.headers['Content-Security-Policy'] = csp
    return response

# Define models
class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)  
    stock_id = db.Column(db.Integer, nullable=False)  
    version = db.Column(db.Integer, nullable=False, default=0)
    name = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    market_cap = db.Column(db.Float, nullable=False, default=1_000) 
    adjusted_price = db.Column(db.Float, nullable=True)  # New column for adjusted price


class SupplyDemand(db.Model):
    supply_demand_id = db.Column(db.Integer, primary_key=True)  # Unique ID for each record
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.stock_id'), nullable=False)  # Related stock
    year = db.Column(db.Integer, nullable=False)  # Year for the modifier
    demand_modifier = db.Column(db.Float, nullable=False, default=1.0)  # Modifier for demand scaling

    stock = db.relationship('Stock', backref=db.backref('supply_demand', lazy=True))

class MarketDynamics(db.Model):
    event_id = db.Column(db.Integer, primary_key=True)  # Unique ID for each market event
    year = db.Column(db.Integer, nullable=False)  # Year the event is triggered
    effect_description = db.Column(db.String(255), nullable=False)  # Short description of the event
    sector = db.Column(db.String(50), nullable=True)  # Affected sector or 'global'
    price_change_factor = db.Column(db.Float, nullable=False, default=1.0)  # Multiplier for stock prices
    demand_change_factor = db.Column(db.Float, nullable=False, default=1.0)  # Multiplier for demand

class Game(db.Model):
    game_id = db.Column(db.Integer, primary_key=True)
    password = db.Column(db.String(50), nullable=False)
    current_year = db.Column(db.Integer, default=1900)
    game_running = db.Column(db.Boolean, default=False)

class Player(db.Model):
    player_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    balance = db.Column(db.Float, nullable=False, default=1000.0)
    stocks_owned = db.Column(db.Integer, nullable=False, default=0)
    portfolio_value = db.Column(db.Float, nullable=False, default=0.0)

class WatchList(db.Model):
    watchlist_id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.player_id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.stock_id'), nullable=False)
    birth_alert = db.Column(db.Boolean, default=False)
    value_alert = db.Column(db.Float, nullable=True)
    value_alert_enabled = db.Column(db.Boolean, default=False)

    player = db.relationship('Player', backref=db.backref('watchlist', lazy=True))
    stock = db.relationship('Stock', backref=db.backref('watchlist', lazy=True), uselist=True)

class HighScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(50), nullable=False)
    total_value = db.Column(db.Float, nullable=False)

class Portfolio(db.Model):
    portfolio_id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.player_id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.stock_id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    year_purchased = db.Column(db.Integer, nullable=False)  # New field

    player = db.relationship('Player', backref=db.backref('portfolio', lazy='joined'))
    stock = db.relationship('Stock', backref=db.backref('portfolio', lazy='joined'), uselist=True)


class CompletedSale(db.Model):
    sale_id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.player_id'), nullable=False)
    stock_name = db.Column(db.String(50), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.stock_id'), nullable=False)
    price_purchased = db.Column(db.Float, nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False)
    price_sold = db.Column(db.Float, nullable=False)
    profit = db.Column(db.Float, nullable=False)
    percentage_return = db.Column(db.Float, nullable=False)
    sale_year = db.Column(db.Integer, nullable=False)  # New column

    player = db.relationship('Player', backref=db.backref('completed_sales', lazy=True))

class HistoricalEvent(db.Model):
    __tablename__ = 'historical_events_feed'

    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer)
    category = db.Column(db.String(50))
    name = db.Column(db.String(100))
    year = db.Column(db.Integer)
    title = db.Column(db.String(200))
    detail = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'stock_id': self.stock_id,
            'name': self.name,
            'year': self.year,
            'title': self.title,
            'detail': self.detail
        }

# Initialize Scheduler with job store
jobstores = {'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')}
scheduler = BackgroundScheduler(jobstores=jobstores)

# Global variable to indicate if the game is running
game_running = False

# Current Year and Time Intervals
current_year = 1900
time_intervals = {
    1900:30,1901:18,1902:18,1903:18,1904:18,1905:18,1906:18,1907:18,1908:18,1909:18,1910:30,1911:18,1912:18,1913:18,1914:18,1915:18,1916:18,1917:18,1918:18,1919:18,1920:30,1921:18,1922:18,1923:18,1924:18,1925:18,1926:18,1927:18,1928:18,1929:18,1930:30,1931:18,1932:18,1933:18,1934:18,1935:18,1936:18,1937:18,1938:18,1939:18,1940:30,1941:18,1942:18,1943:18,1944:18,1945:18,1946:18,1947:18,1948:18,1949:18,1950:30,1951:25,1952:25,1953:25,1954:25,1955:25,1956:25,1957:25,1958:25,1959:25,1960:30,1961:25,1962:25,1963:25,1964:25,1965:25,1966:25,1967:25,1968:25,1969:25,1970:30,1971:25,1972:25,1973:25,1974:25,1975:25,1976:25,1977:25,1978:25,1979:25,1980:30,1981:25,1982:25,1983:25,1984:25,1985:25,1986:25,1987:25,1988:25,1989:25,1990:40,1991:30,1992:30,1993:30,1994:30,1995:30,1996:30,1997:30,1998:30,1999:30,2000:45,2001:30,2002:30,2003:30,2004:30,2005:30,2006:30,2007:30,2008:30,2009:30,2010:45,2011:40,2012:40,2013:40,2014:40,2015:40,2016:40,2017:40,2018:40,2019:40,2020:45,2021:45,2022:45,2023:45,2024:60
}



def start_year_updates():
    global scheduler_running

    # Handle scheduler shutdown or restart conditions
    if scheduler_shutting_down:
        print("Scheduler is shutting down, not scheduling new jobs.")
        return

    # Determine interval and next run time
    interval = time_intervals.get(current_year, 60)  # Default to 60 seconds
    next_run_time = datetime.now() + timedelta(seconds=interval)
    print(f"Scheduling next year update. Next run at {next_run_time} with interval {interval} seconds.")

    try:
        # Start scheduler if not already running
        if not scheduler_running:
            try:
                scheduler.start()
                scheduler_running = True
                print("Scheduler started successfully.")
            except SchedulerAlreadyRunningError:
                print("Scheduler already running.")
            except Exception as e:
                print(f"Error starting scheduler: {e}")
                scheduler_running = False  # Mark scheduler as not running if failed

        # Schedule or update the 'year_update_job'
        if scheduler_running:
            try:
                scheduler.add_job(
                    update_year,
                    'interval',  # Repeatedly execute at defined intervals
                    seconds=interval,
                    id='year_update_job',
                    replace_existing=True
                )
                print(f"Scheduled job 'year_update_job' with interval {interval} seconds.")
            except Exception as e:
                print(f"Error adding job to scheduler: {e}")
        else:
            print("Scheduler is not running, skipping job scheduling.")

        # Log all scheduled jobs for debugging
        check_scheduled_jobs()

    except Exception as overall_error:
        print(f"Unexpected error during start_year_updates: {overall_error}")

def check_scheduled_jobs():
    jobs = scheduler.get_jobs()
    if not jobs:
        print("No jobs are currently scheduled.")
    else:
        for job in jobs:
            try:
                print(f"Job '{job.id}' - next run: {getattr(job, 'next_run_time', 'Unknown')} (trigger: {job.trigger})")
            except AttributeError as e:
                print(f"Error accessing job details: {e}")



def get_adjusted_stock_price(stock, year):
    try:
        base_price = stock.price
        if base_price < 8:
            return base_price

        # Check if the stock is owned by any player
        stock_ownership_count = (
            db.session.query(db.func.sum(Portfolio.quantity))
            .filter(Portfolio.stock_id == stock.stock_id)
            .scalar() or 0
)

        # Market cap and sales logic
        market_cap = stock.market_cap or 1000
        total_sold = (
            db.session.query(db.func.sum(CompletedSale.quantity_sold))
            .filter(CompletedSale.stock_id == stock.stock_id, CompletedSale.sale_year == year)
            .scalar() or 0
        )
        selling_ratio = total_sold / market_cap
        selling_multiplier = max(1.0 - (selling_ratio * 0.1), 0.5)

        # Demand modifier
        supply_demand = db.session.query(SupplyDemand).filter_by(stock_id=stock.stock_id, year=year).first()
        demand_modifier = supply_demand.demand_modifier if supply_demand else 1.0

        # Price change factor
        market_dynamics = db.session.query(MarketDynamics).filter_by(year=year).all()
        price_change_factor = 1.0
        for event in market_dynamics:
            if event.sector is None or event.sector.lower() == stock.category.lower():
                price_change_factor *= event.price_change_factor

        adjusted_price = base_price * selling_multiplier * demand_modifier * price_change_factor
        lower_bound, upper_bound = max(base_price - 10, 0), base_price + 10
        adjusted_price = max(min(adjusted_price, upper_bound), lower_bound)

        # Update adjusted price in the database
        stock.adjusted_price = adjusted_price
        db.session.commit()

        return adjusted_price

    except Exception as e:
        print(f"Error adjusting stock {stock.stock_id}: {e}")
        return stock.price



# AI Basic Buyer
def ai_basic_buyer(player, current_year):
    try:
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
        print(f"[DEBUG] Found {len(stocks)} stocks for year {current_year}.")
        owned_stocks = {item.stock_id: item for item in player.portfolio}
        print(f"[DEBUG] Player {player.name} owns stocks: {list(owned_stocks.keys())}")

        # Buy logic
        for stock in stocks:
            adjusted_price = get_active_price(stock)
            if adjusted_price >= 8 and stock.stock_id not in owned_stocks:
                quantity = 3
                total_cost = adjusted_price * quantity
                if player.balance >= total_cost:
                    player.balance -= total_cost
                    portfolio_item = db.session.query(Portfolio).filter_by(
                        stock_id=stock.stock_id, player_id=player.player_id
                    ).first()

                    if portfolio_item:
                        portfolio_item.quantity += quantity
                    else:
                        portfolio_item = Portfolio(
                            player_id=player.player_id,
                            stock_id=stock.stock_id,
                            quantity=quantity,
                            purchase_price=adjusted_price,
                            year_purchased=current_year
                        )
                        db.session.add(portfolio_item)

                    owned_stocks[stock.stock_id] = portfolio_item

        # Sell logic
        for stock_id, portfolio_item in list(owned_stocks.items()):
            stock = db.session.query(Stock).filter_by(stock_id=stock_id, year=current_year).first()
            if stock:
                adjusted_price = get_active_price(stock)
                if adjusted_price < portfolio_item.purchase_price - 3 or adjusted_price > 65:
                    total_revenue = adjusted_price * portfolio_item.quantity
                    profit = total_revenue - (portfolio_item.purchase_price * portfolio_item.quantity)
                    percentage_return = (profit / (portfolio_item.purchase_price * portfolio_item.quantity)) * 100 if portfolio_item.purchase_price > 0 else 0
                    player.balance += total_revenue

                    # Record sale
                    completed_sale = CompletedSale(
                        player_id=player.player_id,
                        stock_name=stock.name,
                        stock_id=stock_id,
                        price_purchased=portfolio_item.purchase_price,
                        quantity_sold=portfolio_item.quantity,
                        price_sold=adjusted_price,
                        profit=profit,
                        percentage_return=percentage_return,
                        sale_year=current_year
                    )
                    db.session.add(completed_sale)
                    db.session.delete(portfolio_item)

    except Exception as e:
        print(f"[ERROR] Exception occurred in ai_basic_buyer: {e}")
        db.session.rollback()


# AI Top Movers
def ai_top_movers(player, current_year):
    try:
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
        owned_stocks = {item.stock_id: item for item in player.portfolio}
        stock_changes = []

        # Calculate price changes
        for stock in stocks:
            adjusted_price = get_active_price(stock)
            previous_price = db.session.query(Stock.price).filter_by(
                stock_id=stock.stock_id, year=current_year - 1
            ).scalar() or adjusted_price
            stock_changes.append((stock, adjusted_price - previous_price))

        stock_changes_sorted = sorted(stock_changes, key=lambda x: x[1], reverse=True)
        top_movers = stock_changes_sorted[:5]
        biggest_losers = stock_changes_sorted[-5:]

        # Buy top movers
        for stock, _ in top_movers:
            adjusted_price = get_active_price(stock)
            if adjusted_price >= 8 and stock.stock_id not in owned_stocks:
                quantity = 5
                total_cost = adjusted_price * quantity
                if player.balance >= total_cost:
                    player.balance -= total_cost
                    portfolio_item = db.session.query(Portfolio).filter_by(
                        stock_id=stock.stock_id, player_id=player.player_id
                    ).first()

                    if portfolio_item:
                        portfolio_item.quantity += quantity
                    else:
                        portfolio_item = Portfolio(
                            player_id=player.player_id,
                            stock_id=stock.stock_id,
                            quantity=quantity,
                            purchase_price=adjusted_price,
                            year_purchased=current_year
                        )
                        db.session.add(portfolio_item)

                    owned_stocks[stock.stock_id] = portfolio_item

        # Sell biggest losers
        portfolio_item = db.session.query(Portfolio).filter_by(
    stock_id=stock.stock_id, player_id=player.player_id).first()

        if portfolio_item:
                adjusted_price = get_active_price(stock)
                total_revenue = adjusted_price * portfolio_item.quantity
                profit = total_revenue - (portfolio_item.purchase_price * portfolio_item.quantity)
                percentage_return = (profit / (portfolio_item.purchase_price * portfolio_item.quantity)) * 100 if portfolio_item.purchase_price > 0 else 0
                player.balance += total_revenue

                # Record sale
                completed_sale = CompletedSale(
                    player_id=player.player_id,
                    stock_name=stock.name,
                    stock_id=stock.stock_id,
                    price_purchased=portfolio_item.purchase_price,
                    quantity_sold=portfolio_item.quantity,
                    price_sold=adjusted_price,
                    profit=profit,
                    percentage_return=percentage_return,
                    sale_year=current_year
                )
                db.session.add(completed_sale)
                db.session.delete(portfolio_item)
                print(f"[DEBUG] Deleted portfolio item for stock {stock.name} (ID: {stock.stock_id}).")
        else:
                print(f"[DEBUG] Deleted portfolio item for stock {stock.name} (ID: {stock.stock_id}).")
    except Exception as e:
        print(f"[ERROR] Exception occurred in ai_top_movers: {e}")
        db.session.rollback()


def ai_random_trader(player, current_year):
    try:
        # Fetch all stocks for the current year
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()

        # Map owned stocks for the player
        owned_stocks = {item.stock_id: item for item in player.portfolio}

        # List of actions
        actions = ["buy", "sell"]

        for _ in range(10):  # Perform 10 random actions
            action = random.choice(actions)

            if action == "buy":
                stock = random.choice(stocks)
                adjusted_price = get_active_price(stock)

                if adjusted_price >= 8 and stock.stock_id not in owned_stocks:
                    quantity = random.randint(1, 5)
                    total_cost = adjusted_price * quantity
                    if player.balance >= total_cost:
                        player.balance -= total_cost

                        # Check if portfolio item already exists
                        portfolio_item = db.session.query(Portfolio).filter_by(
                            stock_id=stock.stock_id, player_id=player.player_id
                        ).first()

                        if portfolio_item:
                            portfolio_item.quantity += quantity
                            print(f"[DEBUG] Updated portfolio for stock {stock.name} (ID: {stock.stock_id}): New quantity {portfolio_item.quantity}.")
                        else:
                            # Create a new portfolio item
                            portfolio_item = Portfolio(
                                player_id=player.player_id,
                                stock_id=stock.stock_id,
                                quantity=quantity,
                                purchase_price=adjusted_price,
                                year_purchased=current_year
                            )
                            db.session.add(portfolio_item)
                            print(f"[DEBUG] Created new portfolio item for stock {stock.name} (ID: {stock.stock_id}): Quantity {quantity}, Price {adjusted_price}.")

                        owned_stocks[stock.stock_id] = portfolio_item  # Update owned_stocks

            elif action == "sell" and owned_stocks:
                portfolio_item = random.choice(list(owned_stocks.values()))
                stock = db.session.query(Stock).filter_by(stock_id=portfolio_item.stock_id, year=current_year).first()

                if stock:
                    adjusted_price = get_active_price(stock)
                    total_revenue = adjusted_price * portfolio_item.quantity
                    profit = total_revenue - (portfolio_item.purchase_price * portfolio_item.quantity)
                    percentage_return = (
                        (profit / (portfolio_item.purchase_price * portfolio_item.quantity)) * 100
                        if portfolio_item.purchase_price > 0 else 0
                    )
                    player.balance += total_revenue

                    # Record sale
                    completed_sale = CompletedSale(
                        player_id=player.player_id,
                        stock_name=stock.name,
                        stock_id=stock.stock_id,
                        price_purchased=portfolio_item.purchase_price,
                        quantity_sold=portfolio_item.quantity,
                        price_sold=adjusted_price,
                        profit=profit,
                        percentage_return=percentage_return,
                        sale_year=current_year
                    )
                    db.session.add(completed_sale)
                    db.session.delete(portfolio_item)
                    owned_stocks.pop(portfolio_item.stock_id)  # Remove from owned_stocks
                    print(f"[DEBUG] Sold stock {stock.name} (ID: {stock.stock_id}) for Player {player.name}. Total revenue: {total_revenue}.")

    except Exception as e:
        print(f"[ERROR] Exception occurred in ai_random_trader: {e}")
        db.session.rollback()




def ai_value_investor(player, current_year):
    try:
        # Fetch all stocks for the current year
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
        owned_stocks = {item.stock_id: item for item in player.portfolio}

        # Buy stocks under 15
        affordable_stocks = [stock for stock in stocks if 8 <= get_active_price(stock) < 15]
        random.shuffle(affordable_stocks)  # Randomize the affordable stocks
        for stock in affordable_stocks[:5]:  # Limit to top 5 affordable stocks
            adjusted_price = get_active_price(stock)
            if stock.stock_id not in owned_stocks:
                quantity = 5
                total_cost = adjusted_price * quantity
                if player.balance >= total_cost:
                    player.balance -= total_cost

                    # Check if portfolio item already exists
                    portfolio_item = db.session.query(Portfolio).filter_by(
                        stock_id=stock.stock_id, player_id=player.player_id
                    ).first()

                    if portfolio_item:
                        portfolio_item.quantity += quantity
                        print(f"[DEBUG] Updated portfolio for stock {stock.name} (ID: {stock.stock_id}): New quantity {portfolio_item.quantity}.")
                    else:
                        # Create a new portfolio item
                        portfolio_item = Portfolio(
                            player_id=player.player_id,
                            stock_id=stock.stock_id,
                            quantity=quantity,
                            purchase_price=adjusted_price,
                            year_purchased=current_year
                        )
                        db.session.add(portfolio_item)
                        print(f"[DEBUG] Created new portfolio item for stock {stock.name} (ID: {stock.stock_id}): Quantity {quantity}, Price {adjusted_price}.")

                    owned_stocks[stock.stock_id] = portfolio_item  # Update owned_stocks

        # Sell stocks above 60
        for stock_id, portfolio_item in list(owned_stocks.items()):  # Use list() to avoid modifying during iteration
            stock = db.session.query(Stock).filter_by(stock_id=stock_id, year=current_year).first()
            if stock:
                adjusted_price = get_active_price(stock)
                if adjusted_price > 60:
                    total_revenue = adjusted_price * portfolio_item.quantity
                    profit = total_revenue - (portfolio_item.purchase_price * portfolio_item.quantity)
                    percentage_return = (
                        (profit / (portfolio_item.purchase_price * portfolio_item.quantity)) * 100
                        if portfolio_item.purchase_price > 0 else 0
                    )
                    player.balance += total_revenue

                    # Record sale
                    completed_sale = CompletedSale(
                        player_id=player.player_id,
                        stock_name=stock.name,
                        stock_id=stock_id,
                        price_purchased=portfolio_item.purchase_price,
                        quantity_sold=portfolio_item.quantity,
                        price_sold=adjusted_price,
                        profit=profit,
                        percentage_return=percentage_return,
                        sale_year=current_year
                    )
                    db.session.add(completed_sale)
                    db.session.delete(portfolio_item)  # Remove the portfolio item
                    owned_stocks.pop(stock_id)  # Remove from owned_stocks
                    print(f"[DEBUG] Sold stock {stock.name} (ID: {stock_id}) for Player {player.name}. Total revenue: {total_revenue}.")
                else:
                    print(f"[DEBUG] Stock {stock.name} (ID: {stock_id}) not sold. Price {adjusted_price} ≤ 60.")

    except Exception as e:
        print(f"[ERROR] Exception occurred in ai_value_investor: {e}")
        db.session.rollback()



# AI Fully Random
def ai_fully_random(player, current_year):
    try:
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
        owned_stocks = {item.stock_id: item for item in player.portfolio}
        actions = ["buy", "sell"]

        for _ in range(10):  # Perform 10 random actions
            action = random.choice(actions)
            
            if action == "buy":
                stock = random.choice(stocks)
                adjusted_price = get_active_price(stock)
                if adjusted_price >= 8 and stock.stock_id not in owned_stocks:
                    quantity = random.randint(1, 5)
                    total_cost = adjusted_price * quantity
                    if player.balance >= total_cost:
                        player.balance -= total_cost
                        portfolio_item = db.session.query(Portfolio).filter_by(
                            stock_id=stock.stock_id, player_id=player.player_id
                        ).first()

                        if portfolio_item:
                            portfolio_item.quantity += quantity
                            print(f"[DEBUG] Updated portfolio for stock {stock.name} (ID: {stock.stock_id}): New quantity {portfolio_item.quantity}.")
                        else:
                            portfolio_item = Portfolio(
                                player_id=player.player_id,
                                stock_id=stock.stock_id,
                                quantity=quantity,
                                purchase_price=adjusted_price,
                                year_purchased=current_year
                            )
                            db.session.add(portfolio_item)
                            print(f"[DEBUG] Created new portfolio item for stock {stock.name} (ID: {stock.stock_id}): Quantity {quantity}, Price {adjusted_price}.")

                        owned_stocks[stock.stock_id] = portfolio_item  # Update owned_stocks

            elif action == "sell" and owned_stocks:
                portfolio_item = random.choice(list(owned_stocks.values()))
                stock = db.session.query(Stock).filter_by(stock_id=portfolio_item.stock_id, year=current_year).first()

                if stock:
                    adjusted_price = get_active_price(stock)
                    total_revenue = adjusted_price * portfolio_item.quantity
                    profit = total_revenue - (portfolio_item.purchase_price * portfolio_item.quantity)
                    percentage_return = (profit / (portfolio_item.purchase_price * portfolio_item.quantity)) * 100 if portfolio_item.purchase_price > 0 else 0
                    player.balance += total_revenue

                    # Record sale
                    completed_sale = CompletedSale(
                        player_id=player.player_id,
                        stock_name=stock.name,
                        stock_id=portfolio_item.stock_id,
                        price_purchased=portfolio_item.purchase_price,
                        quantity_sold=portfolio_item.quantity,
                        price_sold=adjusted_price,
                        profit=profit,
                        percentage_return=percentage_return,
                        sale_year=current_year
                    )
                    db.session.add(completed_sale)
                    db.session.delete(portfolio_item)
                    owned_stocks.pop(portfolio_item.stock_id)  # Remove from owned_stocks
                    print(f"[DEBUG] Sold stock {stock.name} (ID: {stock.stock_id}) for Player {player.name}. Total revenue: {total_revenue}.")
                else:
                    print(f"[WARNING] Could not find stock data for portfolio item ID: {portfolio_item.stock_id}. Skipping.")

    except Exception as e:
        print(f"[ERROR] Exception occurred in ai_fully_random: {e}")
        db.session.rollback()



def simulate_ai_player_actions(current_year):
    """
    Simulate AI player actions for the given year.
    """
    players = db.session.query(Player).filter(Player.name.in_(AI_PLAYER_NAMES)).all()

    for player in players:
        if player.name == "Bot 1":
            ai_basic_buyer(player, current_year)
        elif player.name == "Bot 2":
            ai_top_movers(player, current_year)
        elif player.name == "Bot 3":
            ai_random_trader(player, current_year)
        elif player.name == "Bot 4":
            ai_value_investor(player, current_year)
        elif player.name == "Bot 5":
            ai_fully_random(player, current_year)

    db.session.commit()


def update_year():
    global current_year

    with app.app_context():
        game = db.session.query(Game).first()
        if not game:
            print("No active game found.")
            return
        if game.current_year >= 2024:
            print("Game has reached the end year.")
            return

        print(f"Executing 'update_year'. Current year: {game.current_year}")
        current_year = game.current_year

        try:
            # Fetch all stocks for the current year
            stocks = db.session.query(Stock).filter_by(year=game.current_year).all()
            if not stocks:
                print(f"No stocks found for year {game.current_year}.")
                return

            for stock in stocks:
                if stock is None:
                    print(f"Error: Stock is None for year {game.current_year}. Skipping.")
                    continue
                    # Calculate adjusted price and update adjusted_price column
                try:
                    adjusted_price = get_adjusted_stock_price(stock, game.current_year)
                    if adjusted_price is not None:
                            stock.adjusted_price = adjusted_price
                    else:
                            print(f"Adjusted price for stock {stock.stock_id} is None. Skipping update.")
                except Exception as stock_error:
                        print(f"Error updating stock {stock.stock_id if stock else 'Unknown'}: {stock_error}")
                        db.session.rollback()

            # Simulate AI player actions
            simulate_ai_player_actions(current_year)

            # Update AI players' portfolio values
            for player in db.session.query(Player).filter(Player.name.in_(AI_PLAYER_NAMES)).all():
                player.portfolio_value = calculate_portfolio_value(player.player_id, current_year)

            # Increment the game year
            game.current_year += 1
            current_year = game.current_year  # Sync global variable
            db.session.commit()
            print(f"Year updated to {game.current_year}.")

        except Exception as e:
            app.logger.error(f"An error occurred: {e}")
            return jsonify({"error": "An unexpected error occurred"}), 500
            db.session.rollback()



def get_active_price(stock):
    """
    Returns the adjusted price if available; otherwise, falls back to the original price.
    """
    try:
        return stock.adjusted_price if hasattr(stock, 'adjusted_price') and stock.adjusted_price is not None else stock.price
    except AttributeError:
        # Handle the case where the stock object does not have adjusted_price
        print(f"Error: Stock {stock} does not have 'adjusted_price' attribute.")
        return stock.price



def error_response(message, status_code=400):
    return jsonify({'status': 'failure', 'message': message}), status_code

def generate_stocks_display(stocks, previous_year_stocks, current_year):
    """
    Generate HTML for displaying stock data with adjusted prices.
    """
    columns = [25, 25, 25, 25, 25, 30, 15, 20]
    stock_slices = []
    start = 0

    for count in columns:
        if start < len(stocks):
            stock_slices.append(stocks[start:start + count])
            start += count

    column_titles = ["Film & Television", "Business", "Science", "Literature", "Music", "Politics", "Jewish Authorities", "Sport"]

    # Top four categories
    top_categories = column_titles[:4]
    top_stock_slices = stock_slices[:4]

    # Bottom four categories
    bottom_categories = column_titles[4:]
    bottom_stock_slices = stock_slices[4:]

    # HTML for top categories
    top_stocks_display = '<table id="topStocksDisplay" style="width: 100%; border-collapse: collapse;"><thead><tr>'
    for title in top_categories:
        top_stocks_display += f'<th colspan="3" class="category-title" style="text-align: center;">{title}</th>'
    top_stocks_display += '</tr><tr>'
    for _ in top_categories:
        top_stocks_display += '<th class="label">Stock</th>'
        top_stocks_display += '<th class="label">Price</th>'
        top_stocks_display += '<th class="label">Change</th>'
    top_stocks_display += '</tr></thead><tbody>'

    max_rows = max(columns[:4])
    for row in range(max_rows):
        top_stocks_display += '<tr>'
        for col in range(len(top_categories)):
            if row < len(top_stock_slices[col]):
                stock = top_stock_slices[col][row]
                adjusted_price = get_active_price(stock)
                prev_price = previous_year_stocks.get(stock.name, adjusted_price)
                change = adjusted_price - prev_price
                percentage_change = (change / prev_price) * 100 if prev_price != 0 else 0
                color = 'green' if change > 0 else 'red' if change < 0 else 'black'

                stock_style = '<strong>' if adjusted_price > 0 else '<i class="unavailable">'
                end_stock_style = '</strong>' if adjusted_price > 0 else '</i>'

                top_stocks_display += f'<td style="border: none;">{stock_style}{stock.name}{end_stock_style}</td>'
                top_stocks_display += f'<td style="border: none;">{stock_style}£{int(adjusted_price)}{end_stock_style}</td>'
                change_display = f'{change:+.0f} ({percentage_change:.1f}%)' if adjusted_price > 0 else '<i class="unavailable">N/A</i>'
                top_stocks_display += f'<td style="color: {color}; border: none;">{change_display}</td>'
            else:
                top_stocks_display += '<td style="border: none;"></td><td style="border: none;"></td><td style="border: none;"></td>'
        top_stocks_display += '</tr>'
    top_stocks_display += '</tbody></table>'

    # HTML for bottom categories
    bottom_stocks_display = '<table id="bottomStocksDisplay" style="width: 100%; border-collapse: collapse; margin-top: 20px;"><thead><tr>'
    for title in bottom_categories:
        bottom_stocks_display += f'<th colspan="3" class="category-title" style="text-align: center;">{title}</th>'
    bottom_stocks_display += '</tr><tr>'
    for _ in bottom_categories:
        bottom_stocks_display += '<th class="label">Stock</th>'
        bottom_stocks_display += '<th class="label">Price</th>'
        bottom_stocks_display += '<th class="label">Change</th>'
    bottom_stocks_display += '</tr></thead><tbody>'

    max_rows = max(columns[4:])
    for row in range(max_rows):
        bottom_stocks_display += '<tr>'
        for col in range(len(bottom_categories)):
            if row < len(bottom_stock_slices[col]):
                stock = bottom_stock_slices[col][row]
                adjusted_price = get_active_price(stock)
                prev_price = previous_year_stocks.get(stock.name, adjusted_price)
                change = adjusted_price - prev_price
                percentage_change = (change / prev_price) * 100 if prev_price != 0 else 0
                color = 'green' if change > 0 else 'red' if change < 0 else 'black'

                stock_style = '<strong>' if adjusted_price > 0 else '<i class="unavailable">'
                end_stock_style = '</strong>' if adjusted_price > 0 else '</i>'

                bottom_stocks_display += f'<td style="border: none;">{stock_style}{stock.name}{end_stock_style}</td>'
                bottom_stocks_display += f'<td style="border: none;">{stock_style}£{int(adjusted_price)}{end_stock_style}</td>'
                change_display = f'{change:+.0f} ({percentage_change:.1f}%)' if adjusted_price > 0 else '<i class="unavailable">N/A</i>'
                bottom_stocks_display += f'<td style="color: {color}; border: none;">{change_display}</td>'
            else:
                bottom_stocks_display += '<td style="border: none;"></td><td style="border: none;"></td><td style="border: none;"></td>'
        bottom_stocks_display += '</tr>'
    bottom_stocks_display += '</tbody></table>'

    return top_stocks_display + bottom_stocks_display


def get_previous_year_stocks(year):
    """
    Fetch the stocks from the previous year as a dictionary of stock name to price.
    """
    previous_year = year - 1
    return {
        stock.name: get_active_price(stock)
        for stock in db.session.query(Stock).filter(Stock.year == previous_year).all()
    }


def generate_player_table(current_year):
    """
    Generate a table of players with their total portfolio value for the given year.
    """
    try:
        players = db.session.query(Player).all()
        player_table = []

        for player in players:
            # Calculate portfolio value for the current year
            portfolio_value = calculate_portfolio_value(player.player_id, current_year)
            total_value = (player.balance or 0) + (portfolio_value or 0)

            player_table.append({
                'player_id': player.player_id,
                'name': player.name,
                'total_value': round(total_value, 1),
            })

        # Sort players by total value in descending order
        return sorted(player_table, key=lambda x: x['total_value'], reverse=True)
    except Exception as e:
        print(f"Error generating player table: {e}")
        return []


def calculate_portfolio_value(player_id, current_year):
    portfolio = db.session.query(Portfolio).filter_by(player_id=player_id).all()
    total_value = 0
    for item in portfolio:
        stock = db.session.query(Stock).filter_by(stock_id=item.stock_id, year=current_year).first()
        if stock:
            adjusted_price = get_active_price(stock)
            total_value += item.quantity * adjusted_price
    return round(total_value, 2)




def generate_stocks_display_data(stocks, previous_year_stocks, current_year):
    """
    Generate structured data for stocks with adjusted prices.
    """
    columns = [25, 25, 25, 25, 25, 30, 15, 20]
    stock_slices = []
    start = 0

    for count in columns:
        if start < len(stocks):
            stock_slices.append(stocks[start:start + count])
            start += count

    column_titles = ["Film & Television", "Business", "Science", "Literature", "Music", "Politics", "Jewish Authorities", "Sport"]

    top_categories = column_titles[:4]
    top_stock_slices = stock_slices[:4]
    bottom_categories = column_titles[4:]
    bottom_stock_slices = stock_slices[4:]

    def process_stock_slices(stock_slices, categories):
        category_data = []
        for category, stocks in zip(categories, stock_slices):
            stocks_data = []
            for stock in stocks:
                adjusted_price = get_active_price(stock)
                prev_price = previous_year_stocks.get(stock.name, adjusted_price)
                change = adjusted_price - prev_price
                percentage_change = (change / prev_price) * 100 if prev_price != 0 else 0
                stocks_data.append({
                    'stock_id': stock.stock_id,
                    'name': stock.name,
                    'price': adjusted_price,
                    'category': stock.category,
                    'previousPrice': prev_price,
                    'change': change,
                    'percentageChange': percentage_change
                })
            category_data.append({
                'category': category,
                'stocks': stocks_data
            })
        return category_data

    top_data = process_stock_slices(top_stock_slices, top_categories)
    bottom_data = process_stock_slices(bottom_stock_slices, bottom_categories)

    return {
        'topCategories': [data['category'] for data in top_data],
        'topStockSlices': [data['stocks'] for data in top_data],
        'bottomCategories': [data['category'] for data in bottom_data],
        'bottomStockSlices': [data['stocks'] for data in bottom_data]
    }



@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react_app(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials, please try again.', 'error')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/game_screen', methods=['GET'])
@admin_required
def game_screen():
    """
    Render the game screen for admin view.
    """
    # Fetch current game year
    game = db.session.query(Game).first()
    current_year = game.current_year if game else "Unknown"

    # Fetch players sorted by portfolio value and balance
    players = db.session.query(Player).order_by((Player.balance + Player.portfolio_value).desc()).all()
    top_5_players = players[:5]

    # Fetch previous year's stocks for comparison
    previous_year_stocks = get_previous_year_stocks(current_year)

    try:
        # Fetch current year stocks
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
        if not stocks:
            stock_changes_display = "<p>No stocks available for the current year.</p>"
            top_5_increases = []
            top_5_decreases = []
        else:
            stock_changes_display = generate_stocks_display(stocks, previous_year_stocks, current_year)

            # Extract data for the top 5 increases and decreases
            stock_changes = [
                {'name': stock.name, 'change': get_active_price(stock) - previous_year_stocks.get(stock.name, 0)}
                for stock in stocks
            ]
            stock_changes_sorted = sorted(stock_changes, key=lambda x: x['change'], reverse=True)
            top_5_increases = stock_changes_sorted[:5]
            top_5_decreases = stock_changes_sorted[-5:]

    except Exception as e:
        stock_changes_display = f"<p>Error loading stocks: {str(e)}</p>"
        top_5_increases = []
        top_5_decreases = []

    # Fetch historical news for the current year
    historical_news = db.session.query(HistoricalEvent).filter_by(year=current_year).all()

    return render_template(
        'game_screen.html',
        current_year=current_year,
        top_5_players=top_5_players,
        top_5_increases=top_5_increases,
        top_5_decreases=top_5_decreases,
        historical_news=historical_news,
        stock_changes_display=stock_changes_display
    )



@app.route('/admin', methods=['GET'])
@admin_required
def admin_dashboard():
    """
    Render the admin dashboard with game and player statistics.
    """
    players = db.session.query(Player).all()

    game = db.session.query(Game).first()
    current_year = game.current_year if game else 1900
    game_running = game.game_running if game else False

    # Fetch previous year's stocks for comparison
    previous_year_stocks = get_previous_year_stocks(current_year)
    try:
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
        stocks_display = generate_stocks_display(stocks, previous_year_stocks, current_year) if stocks else "<p>No stocks available for the current year.</p>"
    except Exception as e:
        stocks_display = f"<p>Error loading stocks: {e}</p>"

    player_table = generate_player_table(current_year)

    return render_template(
        'home.html',
        players=players,
        current_year=current_year,
        stocks_display=stocks_display,
        player_table=player_table,
        game_running=game_running
    )


@app.route('/admin/create_market_event', methods=['POST'])
@admin_required
def create_market_event():
    # Extract form data
    year = int(request.form['year'])
    effect_description = request.form['effect_description']
    sector = request.form['sector'] or None
    price_change_factor = float(request.form['price_change_factor'])
    demand_change_factor = float(request.form['demand_change_factor'])

    # Create new market dynamics event
    new_event = MarketDynamics(
        year=year,
        effect_description=effect_description,
        sector=sector,
        price_change_factor=price_change_factor,
        demand_change_factor=demand_change_factor
    )
    db.session.add(new_event)
    db.session.commit()

    flash('Market event created successfully!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/player/<int:player_id>', methods=['GET'])
@admin_required
def admin_player_details(player_id):
    """
    Fetch and display details of a specific player's portfolio and transactions.
    """
    global current_year

    player = db.session.query(Player).filter_by(player_id=player_id).first()
    if not player:
        flash('Player not found', 'error')
        return redirect(url_for('admin_dashboard'))

    portfolio_items = db.session.query(Portfolio).filter_by(player_id=player_id).all()
    completed_sales = db.session.query(CompletedSale).filter_by(player_id=player_id).all()

    portfolio = []
    for item in portfolio_items:
        stock = db.session.query(Stock).filter_by(stock_id=item.stock_id, year=current_year).first()
        if stock:
            adjusted_price = get_adjusted_stock_price(stock, current_year)
            current_value = adjusted_price * item.quantity
            potential_profit = current_value - (item.purchase_price * item.quantity)
            portfolio.append({
                'stock_name': stock.name,
                'quantity': item.quantity,
                'current_value': current_value,
                'potential_profit': potential_profit,
            })

    return render_template(
        'player_details.html',
        player=player,
        portfolio=portfolio,
        completed_sales=completed_sales
    )


@app.route('/get_player_table')
def get_player_table():
    try:
        game = db.session.query(Game).first()
        if not game:
            return jsonify({'error': 'Game not initialized', 'player_table': []}), 500
        current_year = game.current_year

        # Generate the player table and limit it to the top 5
        player_table = generate_player_table(current_year)[:5]
        return jsonify({'player_table': player_table})
    except Exception as e:
        return jsonify({'error': str(e), 'player_table': []}), 500


@app.route('/stop_game', methods=['POST'])
@admin_required
def stop_game():
    global game_running

    try:
        # Fetch all players
        players = db.session.query(Player).all()

        # Fetch current year
        game = db.session.query(Game).first()
        current_year = game.current_year

        # Iterate through all players and sell their stocks
        for player in players:
            portfolio_items = db.session.query(Portfolio).filter_by(player_id=player.player_id).all()
            for item in portfolio_items:
                # Calculate adjusted stock price
                stock = db.session.query(Stock).filter_by(stock_id=item.stock_id, year=current_year).first()
                if stock:
                    adjusted_price = get_adjusted_stock_price(stock, current_year)

                    # Sell all stocks in the portfolio
                    total_revenue = adjusted_price * item.quantity
                    player.balance += total_revenue

                    # Track completed sale
                    profit = total_revenue - (item.purchase_price * item.quantity)
                    percentage_return = (profit / (item.purchase_price * item.quantity)) * 100 if item.purchase_price > 0 else 0

                    completed_sale = CompletedSale(
                        player_id=player.player_id,
                        stock_name=stock.name,
                        stock_id=item.stock_id,
                        price_purchased=item.purchase_price,
                        quantity_sold=item.quantity,
                        price_sold=adjusted_price,
                        profit=profit,
                        percentage_return=percentage_return,
                        sale_year=current_year  # Add the current year
                    )
                    db.session.add(completed_sale)

                    # Remove the portfolio item
                    db.session.delete(item)

        # Stop the game and mark it as not running
        game.game_running = False
        game_running = False

        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Game stopped successfully.'}), 200

    except Exception as e:
        db.session.rollback()
        print(f"Error stopping the game: {e}")
        return jsonify({'status': 'failure', 'message': 'Error stopping the game.'}), 500

@app.route('/set_year', methods=['POST'])
def set_year():
    global current_year
    try:
        year = request.form['year']
        if not year.isdigit() or not 1900 <= int(year) <= 2024:
            # If the year is out of range, set a flash message and return to the home page
            flash('Year out of range. Please enter a year between 1900 and 2024.', 'error')
            return redirect(url_for('admin_dashboard'))
        current_year = int(year)

        # Update the game with the selected year
        game = db.session.query(Game).first()
        if game:
            game.current_year = current_year
            db.session.commit()

        # Prepare the stocks for the selected year
        stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
        previous_year_stocks = get_previous_year_stocks(current_year)
        stocks_display = generate_stocks_display(stocks, previous_year_stocks,current_year)
        player_table = generate_player_table(current_year)

        # Return to the home page to allow starting the game with the selected year
        return redirect(url_for('admin_dashboard'))

    except ValueError:
        flash('Invalid input. Please enter a valid year.', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/start_game', methods=['POST'])
def start_game():
    global game_running, current_year
    if not game_running:
        game_running = True

        # Retrieve the game instance
        game = db.session.query(Game).first()
        if game:
            # Set the game to start at the currently set year
            current_year = game.current_year
            game.current_year = current_year
            game.game_running = game_running
            db.session.commit()

                # Start year updates
        start_year_updates()
        return redirect(url_for('admin_dashboard'))

    return redirect(url_for('admin_dashboard'))

@app.route('/restart_game', methods=['POST'])
def restart_game():
    global current_year, game_running
    game_running = False
    current_year = 1900

    # Clear the current session data
    print("Clearing session for reason: restart game")  # Add this before session.clear() or session.pop()
    session.clear()

    game = db.session.query(Game).first()
    if game:
        game.current_year = current_year
        game.password = 'default_password'  # Reset password to default
        game.game_running = game_running
        db.session.commit()

    
    # Reset player data
    db.session.query(Player).delete()
    db.session.query(Portfolio).delete()
    db.session.query(CompletedSale).delete()
    db.session.query(WatchList).delete()
    db.session.commit()

    # Reset AI players and scheduler
    reset_ai_players_and_scheduler()

    # Redirect back to the admin dashboard
    return redirect(url_for('admin_dashboard'))

placeholder_password = generate_password_hash("ai_placeholder_password")

def reset_ai_players_and_scheduler():
    # Add AI Players
    for name in AI_PLAYER_NAMES:
        player = db.session.query(Player).filter_by(name=name).first()
        if not player:
            new_player = Player(
                name=name,
                balance=1000,
                portfolio_value=0
            )
            db.session.add(new_player)

    db.session.commit()  # Commit changes after adding all AI players

    # Stop the scheduler
    try:
        if scheduler.running:
            scheduler.shutdown()
    except SchedulerAlreadyRunningError:
        print("Scheduler wasn't running, skipping shutdown.")

    # Create a new session after clearing
    session.permanent = True  # Mark the new session as permanent

    return redirect(url_for('admin_dashboard'))




@app.route('/get_next_interval', methods=['GET'])
def get_next_interval():
    interval = time_intervals.get(current_year, 60)
    return jsonify(interval=interval)

@app.route('/get_current_year', methods=['GET'])
def get_current_year():
    global current_year
    game = db.session.query(Game).first()
    if game:
        current_year = game.current_year
    return jsonify(current_year=current_year, game_running=game_running)

@app.route('/update_stocks', methods=['GET'])
def update_stocks():
    """
    Update stock data for the current year and generate updated displays.
    """
    global current_year

    # Fetch the previous year's stock data
    previous_year_stocks = get_previous_year_stocks(current_year)

    # Fetch the current year's stock data
    stocks = db.session.query(Stock).filter(Stock.year == current_year).all()

    # Generate stocks display with current year
    stocks_display = generate_stocks_display(stocks, previous_year_stocks, current_year)

    # Generate player table with the current year
    player_table = generate_player_table(current_year)

    return jsonify(stocks_display=stocks_display, player_table=player_table)



@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    team_name = data.get('teamName')

    if not team_name:
        return jsonify({'message': 'Team name is required'}), 400

    player = Player.query.filter_by(name=team_name).first()

    if not player:
        # Create new player
        new_player = Player(name=team_name, balance=1000)
        db.session.add(new_player)
        db.session.commit()
        player = new_player

    # Generate JWT token
    token = jwt.encode({
        'player_id': player.player_id,
        'exp': datetime.now(timezone.utc) + timedelta(hours=3)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({'token': token})



@app.route('/api/categories', methods=['GET'])
def get_categories():
    category_list = [
        "film_&_television", "business", "science", 
        "literature", "music", "politics", 
        "jewish_authorities", "sport"
    ]
    return jsonify(category_list)

@app.route('/api/update_portfolio', methods=['POST'])
@token_required
def update_portfolio(current_user):
    """
    Update the player's portfolio based on buying or selling stocks.
    """
    global current_year
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({'status': 'failure', 'message': 'Invalid data format'}), 400

    player = current_user
    if not player:
        return jsonify({'status': 'failure', 'message': 'Player not found'}), 404

    for stock_id_str, change in data.items():
        try:
            stock_id = int(stock_id_str)
        except ValueError:
            return jsonify({'status': 'failure', 'message': f"Invalid stock ID: {stock_id_str}"}), 400

        stock = db.session.query(Stock).filter_by(stock_id=stock_id, year=current_year).first()
        if not stock:
            return jsonify({'status': 'failure', 'message': f"Stock ID {stock_id} not found"}), 404

        adjusted_price = get_adjusted_stock_price(stock, current_year)

        # Handle buying stocks
        if change > 0:
            total_cost = adjusted_price * change
            if player.balance >= total_cost:
                player.balance -= total_cost
                portfolio_item = db.session.query(Portfolio).filter_by(player_id=player.player_id, stock_id=stock_id).first()
                if portfolio_item:
                    portfolio_item.quantity += change
                else:
                    portfolio_item = Portfolio(
                        player_id=player.player_id,
                        stock_id=stock_id,
                        quantity=change,
                        purchase_price=adjusted_price,
                        year_purchased=current_year
                    )
                    db.session.add(portfolio_item)
            else:
                return jsonify({'status': 'failure', 'message': f"Not enough balance to buy {change} shares of {stock.name}"}), 400

        # Handle selling stocks
        elif change < 0:
            portfolio_item = db.session.query(Portfolio).filter_by(player_id=player.player_id, stock_id=stock_id).first()
            if not portfolio_item or portfolio_item.quantity < abs(change):
                return jsonify({'status': 'failure', 'message': f"Not enough shares of {stock.name} to sell"}), 400

            total_revenue = adjusted_price * abs(change)
            player.balance += total_revenue
            portfolio_item.quantity += change

            # Track completed sale
            profit = total_revenue - abs(change) * portfolio_item.purchase_price
            percentage_return = (profit / (abs(change) * portfolio_item.purchase_price)) * 100 if portfolio_item.purchase_price > 0 else 0

            completed_sale = CompletedSale(
                player_id=player.player_id,
                stock_name=stock.name,
                stock_id=stock_id,
                price_purchased=portfolio_item.purchase_price,
                quantity_sold=abs(change),
                price_sold=adjusted_price,
                profit=profit,
                percentage_return=percentage_return,
                sale_year=current_year
            )
            db.session.add(completed_sale)

            # Remove the portfolio entry if all shares are sold
            if portfolio_item.quantity == 0:
                db.session.delete(portfolio_item)
            else:
                print(f"Portfolio item for stock_id={stock.stock_id} not found.")

    db.session.commit()
    return jsonify({'status': 'success'})



def determine_category(stock_id):
    category_ranges = {
        "film_&_television": (1, 25),
        "business": (26, 50),
        "science": (51, 75),
        "literature": (76, 100),
        "music": (101, 125),
        "politics": (126, 155),
        "jewish_authorities": (156, 170),
        "sport": (171, 190),
    }
    for category, (start, end) in category_ranges.items():
        if start <= stock_id < end:
            return category.replace('_', ' ')
    return "Unknown"

@app.route('/api/player_info', methods=['GET'])
@token_required
def player_info(current_user):
    if not current_user:
        return jsonify({'status': 'failure', 'message': 'Player not found'}), 404

    player = current_user

    portfolio_value = 0
    total_stocks_owned = 0

    portfolio = db.session.query(Portfolio).filter_by(player_id=player.player_id).all()
    for item in portfolio:
        current_year_stock = db.session.query(Stock).filter_by(stock_id=item.stock_id, year=current_year).first()
        if current_year_stock:
            stock_current_price = current_year_stock.price
            portfolio_value += item.quantity * stock_current_price
            total_stocks_owned += item.quantity

    player.portfolio_value = portfolio_value
    player.stocks_owned = total_stocks_owned
    db.session.commit()

    completed_sales = [
        {
            'stock_name': sale.stock_name,
            'price_purchased': sale.price_purchased,
            'quantity_sold': sale.quantity_sold,
            'price_sold': sale.price_sold,
            'profit': sale.profit,
            'percentage_return': sale.percentage_return
        }
        for sale in player.completed_sales
    ]

    return jsonify({
        'teamName': player.name,
        'stocks_owned': player.stocks_owned,
        'balance': player.balance,
        'portfolio_value': player.portfolio_value,
        'game_running': game_running,
        'current_year': current_year,
        'completed_sales': completed_sales
    })


@app.route('/api/player_portfolio', methods=['GET'])
@token_required
def player_portfolio(current_user):
    """
    Retrieve the current player's portfolio with stock details.
    """
    global current_year

    player = current_user
    if not player:
        return jsonify({'status': 'failure', 'message': 'Player not found'}), 404

    portfolio = db.session.query(Portfolio).filter_by(player_id=player.player_id).all()

    if not portfolio:
        return jsonify([])

    shares_owned = []

    for item in portfolio:
        stock = db.session.query(Stock).filter_by(stock_id=item.stock_id, year=current_year).first()

        if stock:
            adjusted_price = get_adjusted_stock_price(stock, current_year)
            current_value = adjusted_price * item.quantity
        else:
            adjusted_price = 0
            current_value = 0

        shares_owned.append({
            'stock_id': item.stock_id,
            'name': stock.name if stock else "Unknown",
            'category': determine_category(item.stock_id),
            'owned': item.quantity,
            'purchase_price': item.purchase_price,
            'current_value': current_value,
            'year_purchased': item.year_purchased,
            'current_year': current_year
        })

    return jsonify(shares_owned)




@app.route('/api/stocks/<category>', methods=['GET'])
def stocks_by_category(category):
    """
    Fetch stocks belonging to a specific category for the current year.
    """
    global current_year

    category_ranges = {
        "film_&_television": (1, 25),
        "business": (26, 50),
        "science": (51, 75),
        "literature": (76, 100),
        "music": (101, 125),
        "politics": (126, 155),
        "jewish_authorities": (156, 170),
        "sport": (171, 190),
    }

    if category in category_ranges:
        start, end = category_ranges[category]
        stocks = db.session.query(Stock).filter(
            Stock.stock_id >= start,
            Stock.stock_id < end,
            Stock.year == current_year
        ).all()
        stock_list = [
            {'stock_id': stock.stock_id, 'name': stock.name, 'price': get_active_price(stock)}
            for stock in stocks
        ]
        return jsonify(stock_list)
    else:
        return jsonify({'status': 'failure', 'message': 'Invalid category'}), 400


@app.route('/api/stock_history/<int:stock_id>', methods=['GET'])
def stock_history(stock_id):
    global current_year
    session = RawSQLSession()  # Use the SQLAlchemy session
    try:
        print(f"Current game year: {current_year}")

        # Execute raw SQL directly to fetch all stock data up to and including the current year
        sql = text("SELECT * FROM stock WHERE stock_id = :stock_id AND year <= :current_year ORDER BY year")
        stock_history_data = session.execute(sql, {'stock_id': stock_id, 'current_year': current_year}).fetchall()

        # Create the history list outside of the loop
        history = [{'year': row.year, 'price': row.price} for row in stock_history_data]

        return jsonify(history)
    except Exception as e:
        return jsonify({'status': 'failure', 'message': str(e)}), 500
    finally:
        session.close()



@app.route('/api/verify_stock_data', methods=['GET'])
def verify_stock_data():
    session = RawSQLSession()  # Use the SQLAlchemy session
    try:
        sql = text("SELECT * FROM stock WHERE stock_id = :stock_id ORDER BY year")
        result = session.execute(sql, {'stock_id': 1}).fetchall()
        for row in result:
            print(f"Year: {row[2]}, Price: {row[3]}")  # Using integer indices
        return jsonify([{'year': row[2], 'price': row[3]} for row in result])
    finally:
        session.close()

@app.route('/api/stocks_data')
def get_stocks_data():
    """
    Fetch all stocks' data for the current year, including adjusted prices.
    """
    previous_year_stocks = get_previous_year_stocks(current_year)
    stocks = db.session.query(Stock).filter(Stock.year == current_year).all()
    stocks_data = generate_stocks_display_data(stocks, previous_year_stocks, current_year)
    return jsonify(stocks_data)


@app.route('/api/historical_events', methods=['GET'])
def get_historical_events():
    year = request.args.get('year')
    if year:
        events = HistoricalEvent.query.filter_by(year=year).all()
    else:
        events = []
    return jsonify([event.to_dict() for event in events])

@app.route('/api/game_status', methods=['GET'])
def get_game_status():
    game = Game.query.first()
    if game:
        return jsonify({'current_year': game.current_year})
    else:
        return jsonify({'current_year': 1900}), 404  # Fallback if no game found


@app.route('/test_session')
def test_session():
    player_id = session.get('player_id')
    return f"Player ID in session: {player_id}" if player_id else "No player ID in session"

@app.route('/api/historical_events_for_portfolio', methods=['GET'])
@token_required
def historical_events_for_portfolio(current_user):
    current_year = Game.query.first().current_year
    portfolio_stocks = [stock.stock_id for stock in current_user.portfolio]
    events = HistoricalEvent.query.filter(
        HistoricalEvent.year == current_year,
        HistoricalEvent.stock_id.in_(portfolio_stocks)
    ).all()
    return jsonify([event.to_dict() for event in events])

@app.route('/api/watch_list', methods=['GET'])
@token_required
def get_watch_list(current_user):
    # Fetch the user's watch list from the database
    watch_list_items = db.session.query(WatchList).filter_by(player_id=current_user.player_id).all()

    # If no items found, return an empty list
    if not watch_list_items:
        return jsonify([])

    # Format the response
    watch_list = [
        {
            'stock_id': item.stock_id,
            'birthAlert': item.birth_alert,
            'valueAlert': item.value_alert,
            'valueAlertEnabled': item.value_alert_enabled
        }
        for item in watch_list_items
    ]

    return jsonify(watch_list)

@app.route('/api/watch_list', methods=['POST'])
@token_required
def add_to_watch_list(current_user):
    data = request.get_json()
    stock_id = data.get('stock_id')
    birth_alert = data.get('birthAlert', False)
    value_alert = data.get('valueAlert', None)
    value_alert_enabled = data.get('valueAlertEnabled', False)

    # Check if both alerts are off, if so, delete the watchlist entry
    if not birth_alert and not value_alert_enabled:
        watch_list_item = db.session.query(WatchList).filter_by(
            player_id=current_user.player_id, stock_id=stock_id).first()
        if watch_list_item:
            db.session.delete(watch_list_item)
            db.session.commit()
            return jsonify({'status': 'deleted'})
        else:
            return jsonify({'status': 'not_found'})
    else:
        # Otherwise, update or add the watchlist entry
        watch_list_item = db.session.query(WatchList).filter_by(
            player_id=current_user.player_id, stock_id=stock_id).first()
        if watch_list_item:
            watch_list_item.birth_alert = birth_alert
            watch_list_item.value_alert = value_alert
            watch_list_item.value_alert_enabled = value_alert_enabled
        else:
            watch_list_item = WatchList(
                player_id=current_user.player_id,
                stock_id=stock_id,
                birth_alert=birth_alert,
                value_alert=value_alert,
                value_alert_enabled=value_alert_enabled
            )
            db.session.add(watch_list_item)

        db.session.commit()
        return jsonify({'status': 'success'})




@app.route('/api/stocks_with_history', methods=['GET'])
@token_required
def get_stocks_with_history(current_user):
    global current_year
    previous_year = current_year - 1

    # Query current year's stocks and their prices
    current_stocks = db.session.query(Stock.stock_id, Stock.name, Stock.price).filter_by(year=current_year).all()

    # Query previous year's stocks and their prices
    previous_stocks = db.session.query(Stock.stock_id, Stock.price).filter_by(year=previous_year).all()

    # Create a dictionary to map stock_id to previous year's price
    previous_prices = {stock.stock_id: stock.price for stock in previous_stocks}

    # Construct the response data with current and previous prices
    stocks_data = [
        {
            'stock_id': stock.stock_id,
            'name': stock.name,
            'price': get_active_price(stock),
            'previousPrice': previous_prices.get(stock.stock_id, 0)  # If no previous price found, default to 0
        }
        for stock in current_stocks
    ]

    return jsonify(stocks_data)



@app.route('/admin/record_scores', methods=['POST'])
@admin_required
def record_scores():
    players = db.session.query(Player).all()
    for player in players:
        total_value = player.balance + player.portfolio_value
        high_score = HighScore(team_name=player.name, total_value=total_value)
        db.session.add(high_score)
    db.session.commit()
    flash('Scores recorded successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/leaderboard', methods=['GET'])
@admin_required
def leaderboard():
    high_scores = db.session.query(HighScore).order_by(HighScore.total_value.desc()).all()
    return render_template('leaderboard.html', high_scores=high_scores)

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()  # Rollback if an error occurs during a request
    return render_template('500.html'), 500

#def clean_up_expired_sessions():
#    now = datetime.now(timezone.utc)  # Use timezone-aware UTC datetime
#    db.session.execute(delete(Session).where(Session.expiry < now))  # Here, `Session` should be your session model, so replace it if necessary.
#    db.session.commit()


gunicorn -w 4 -b 0.0.0.0:8000 app:app
