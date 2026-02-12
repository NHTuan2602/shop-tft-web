import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = "0938899046aA@@"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cấu hình upload ảnh
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    balance = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, default=False)
    bought_accounts = db.relationship('Account', backref='owner', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(200), default="https://via.placeholder.com/150")
    # Quan hệ: 1 Sản phẩm có nhiều Acc trong kho
    accounts = db.relationship('Account', backref='product', lazy=True)

    @property
    def stock(self):
        # Đếm số lượng acc CHƯA BÁN thuộc sản phẩm này
        return Account.query.filter_by(product_id=self.id, is_sold=False).count()

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(50), nullable=False)
    is_sold = db.Column(db.Boolean, default=False)
    
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

# --- UTILS & DECORATORS ---
@login_manager.user_loader
def load_user(u_id): return User.query.get(int(u_id))

@app.template_filter('vnd')
def format_vnd(v): return "{:,.0f} đ".format(v).replace(",", ".")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Khu vực cấm! Chỉ Admin được vào.", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---

@app.route('/')
def index():
    # Trang chủ hiển thị danh sách SẢN PHẨM
    products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/buy-product/<int:product_id>')
@login_required
def buy_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # 1. Kiểm tra tiền
    if current_user.balance < product.price:
        flash("Số dư không đủ. Vui lòng nạp thêm!", "error")
        return redirect(url_for('recharge'))
    
    # 2. Lấy 1 acc trong kho ra (Lấy cái đầu tiên chưa bán)
    acc = Account.query.filter_by(product_id=product.id, is_sold=False).first()
    
    if not acc:
        flash("Sản phẩm này vừa hết hàng!", "error")
        return redirect(url_for('index'))
    
    # 3. Giao dịch
    current_user.balance -= product.price
    acc.is_sold = True
    acc.owner_id = current_user.id
    db.session.commit()
    
    return render_template('success.html', account=acc, product=product)

# --- ADMIN ROUTES ---

@app.route('/admin')
@login_required
@admin_required
def admin():
    products = Product.query.all()
    return render_template('admin.html', products=products)

@app.route('/admin/add-product', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = int(request.form['price'])
        
        # Xử lý ảnh
        image_url = "https://via.placeholder.com/150"
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = '/static/uploads/' + filename
        
        new_prod = Product(name=name, price=price, image_url=image_url)
        db.session.add(new_prod)
        db.session.commit()
        flash("Đã tạo sản phẩm! Hãy nhập acc vào kho.", "success")
        return redirect(url_for('admin_import'))
    return render_template('add_product.html')

@app.route('/admin/edit-product/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.price = int(request.form['price'])
        
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                product.image_url = '/static/uploads/' + filename
        
        db.session.commit()
        flash("Cập nhật thành công!", "success")
        return redirect(url_for('admin'))
    return render_template('edit_product.html', product=product)

@app.route('/admin/delete-product/<int:product_id>')
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    # Xóa toàn bộ acc trong kho của sản phẩm này trước
    Account.query.filter_by(product_id=product.id).delete()
    # Xóa sản phẩm
    db.session.delete(product)
    db.session.commit()
    flash("Đã xóa sản phẩm và toàn bộ kho hàng!", "success")
    return redirect(url_for('admin'))

@app.route('/admin/import', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_import():
    products = Product.query.all()
    if request.method == 'POST':
        product_id = int(request.form['product_id'])
        raw_data = request.form['raw_data']
        lines = raw_data.strip().split('\n')
        count = 0
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 2:
                # user|pass
                new_acc = Account(username=parts[0].strip(), password=parts[1].strip(), product_id=product_id)
                db.session.add(new_acc)
                count += 1
        db.session.commit()
        flash(f"Đã nhập {count} acc vào kho!", "success")
        return redirect(url_for('admin'))
    return render_template('admin_import.html', products=products)

# --- AUTH & USER ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash("Sai thông tin!", "error")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # --- BƯỚC 1: KIỂM TRA TRÙNG TÊN ---
        # Tìm trong database xem có ai dùng tên này chưa
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            # Nếu tìm thấy -> Báo lỗi và bắt nhập lại
            flash("Tên đăng nhập này đã tồn tại! Vui lòng chọn tên khác.", "error")
            return redirect(url_for('register'))
        
        # --- BƯỚC 2: NẾU KHÔNG TRÙNG THÌ MỚI LƯU ---
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw, is_admin=False)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Đăng ký thành công! Hãy đăng nhập.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            # Phòng trường hợp lỗi khác
            db.session.rollback()
            flash(f"Lỗi không xác định: {str(e)}", "error")
            return redirect(url_for('register'))
            
    return render_template('register.html')
@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/recharge')
@login_required
def recharge(): return render_template('recharge.html')

@app.route('/admin-add-money', methods=['POST'])
@login_required
def admin_add_money():
    current_user.balance += int(request.form['amount']); db.session.commit()
    return redirect(url_for('recharge'))

@app.route('/my-orders')
@login_required
def my_orders():
    return render_template('my_orders.html', accounts=Account.query.filter_by(owner_id=current_user.id).all())

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            db.session.add(User(username="admin", password=generate_password_hash("admin123", method='pbkdf2:sha256'), is_admin=True))
            db.session.commit()

if __name__ == '__main__': init_db(); app.run(debug=False, host='0.0.0.0')