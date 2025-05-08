from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import pymysql
import requests

pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.secret_key = 'secret_key'

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/maay_database1'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crypto_name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    user = db.relationship('User', backref=db.backref('favorites', lazy=True))

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crypto_name = db.Column(db.String(100), nullable=False)
    amount_owned = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('portfolio', lazy=True))

# Routes
@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for('dashboard'))
    return render_template("index.html", active_tab="login")

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        session['username'] = username
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid username or password.', 'danger')
        return render_template('index.html', active_tab="login")

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user:
        flash('Username already exists.', 'danger')
        return render_template('index.html', active_tab="register")
    else:
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        session['username'] = username
        return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('home'))

    user = User.query.filter_by(username=session['username']).first()
    portfolio = user.portfolio

    # Prepare data for the pie chart
    labels = [item.crypto_name for item in portfolio]
    data = [item.amount_owned for item in portfolio]

    return render_template('dashboard.html', username=user.username, labels=labels, data=data)

@app.route('/cryptos')
def cryptos():
    if 'username' not in session:
        return redirect(url_for('home'))

    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 10,
        'page': 1
    }

    response = requests.get(url, params=params)
    crypto_data = response.json() if response.status_code == 200 else []

    return render_template('cryptos.html', cryptos=crypto_data)

@app.route('/add_favorite_from_api', methods=['POST'])
def add_favorite_from_api():
    if 'username' not in session:
        return redirect(url_for('home'))

    crypto_name = request.form['crypto_name']
    image_url = request.form['image_url']

    user = User.query.filter_by(username=session['username']).first()
    existing = Favorite.query.filter_by(user_id=user.id, crypto_name=crypto_name).first()

    if not existing:
        new_favorite = Favorite(crypto_name=crypto_name, image_url=image_url, user_id=user.id)
        db.session.add(new_favorite)
        db.session.commit()

    return redirect(url_for('favorites_page'))

@app.route('/add_to_portfolio', methods=['POST'])
def add_to_portfolio():
    if 'username' not in session:
        return redirect(url_for('home'))

    crypto_name = request.form['crypto_name']
    amount = float(request.form['amount'])
    image_url = request.form.get('image_url', '')

    user = User.query.filter_by(username=session['username']).first()
    existing = Portfolio.query.filter_by(user_id=user.id, crypto_name=crypto_name).first()

    if existing:
        existing.amount_owned = amount
    else:
        new_entry = Portfolio(crypto_name=crypto_name, amount_owned=amount, image_url=image_url, user_id=user.id)
        db.session.add(new_entry)

    db.session.commit()
    return redirect(url_for('portfolio_page'))

@app.route('/favorites')
def favorites_page():
    if 'username' not in session:
        return redirect(url_for('home'))

    user = User.query.filter_by(username=session['username']).first()
    return render_template('favorites.html', favorites=user.favorites, username=user.username)

@app.route('/portfolio')
def portfolio_page():
    if 'username' not in session:
        return redirect(url_for('home'))

    user = User.query.filter_by(username=session['username']).first()
    portfolio = user.portfolio

    # Fetch current prices for each cryptocurrency in the portfolio
    crypto_ids = [coin.crypto_name.lower() for coin in portfolio]
    url = 'https://api.coingecko.com/api/v3/simple/price'
    params = {
        'ids': ','.join(crypto_ids),
        'vs_currencies': 'usd'
    }
    response = requests.get(url, params=params)
    prices = response.json()

    # Calculate portfolio value and individual coin values
    portfolio_value = 0
    for coin in portfolio:
        coin_price = prices.get(coin.crypto_name.lower(), {}).get('usd', 0)
        coin_value = coin_price * coin.amount_owned
        coin.current_value = coin_value
        portfolio_value += coin_value

    return render_template('portfolio.html', portfolio=portfolio, username=user.username, portfolio_value=portfolio_value)

@app.route('/delete_favorite/<int:fav_id>', methods=['POST'])
def delete_favorite(fav_id):
    if 'username' not in session:
        return redirect(url_for('home'))

    try:
        fav = Favorite.query.get_or_404(fav_id)
        user = User.query.filter_by(username=session['username']).first()

        if fav.user_id == user.id:
            db.session.delete(fav)
            db.session.commit()
            flash('Coin deleted from favorites successfully!', 'success')
        else:
            flash('You are not authorized to delete this favorite', 'danger')

    except Exception as e:
        flash('Error deleting favorite', 'danger')
    
    return redirect(url_for('favorites_page'))

@app.route('/update_portfolio/<int:entry_id>', methods=['POST'])
def update_portfolio(entry_id):
    if 'username' not in session:
        return redirect(url_for('home'))

    try:
        new_amount = float(request.form['new_amount'])
        
        if new_amount <= 0:
            flash('Amount must be a positive number', 'danger')
            return redirect(url_for('portfolio_page'))

        entry = Portfolio.query.get_or_404(entry_id)
        user = User.query.filter_by(username=session['username']).first()

        if entry.user_id == user.id:
            entry.amount_owned = new_amount
            db.session.commit()
            flash('Coin updated successfully!', 'success')
        else:
            flash('You are not authorized to update this entry', 'danger')

    except ValueError:
        flash('Invalid amount entered', 'danger')
    
    return redirect(url_for('portfolio_page'))

@app.route('/delete_portfolio/<int:portfolio_id>', methods=['POST'])
def delete_portfolio(portfolio_id):
    if 'username' not in session:
        return redirect(url_for('home'))

    try:
        portfolio_item = Portfolio.query.get_or_404(portfolio_id)
        user = User.query.filter_by(username=session['username']).first()

        if portfolio_item.user_id == user.id:
            db.session.delete(portfolio_item)
            db.session.commit()
            flash('Coin deleted from portfolio successfully!', 'success')
        else:
            flash('You are not authorized to delete this entry', 'danger')

    except Exception as e:
        flash('Error deleting portfolio entry', 'danger')
    
    return redirect(url_for('portfolio_page'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)