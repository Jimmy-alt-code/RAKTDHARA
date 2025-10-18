from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

# Ensure .env is loaded from the project directory regardless of where the server is started
_env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=_env_path, override=True)
app = Flask(__name__, static_folder='.', static_url_path='')

# Configure CORS to allow requests from the deployed frontend
# FRONTEND_URL: optional env var you can set to your Vercel domain (https://your-site.vercel.app)
# VERCEL may set VERCEL_URL (without scheme) for preview; we accept either.
frontend_url = os.getenv('FRONTEND_URL') or os.getenv('VERCEL_URL')
if frontend_url:
    if not frontend_url.startswith('http'):
        frontend_url = f"https://{frontend_url}"
    # allow localhost for local testing as well
    cors_origins = [frontend_url, 'http://127.0.0.1:5000', 'http://localhost:5000']
    CORS(app, origins=cors_origins)
else:
    # fallback: allow all origins (useful until you set FRONTEND_URL in production)
    CORS(app)

# Database configuration - use DATABASE_URL in production (Render/Heroku style)
# If not set, fall back to a local sqlite file for development/testing.
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///mvp_blood_bank.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Models
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Donor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    blood_type = db.Column(db.String(5), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(60), nullable=False)
    user_type = db.Column(db.String(20), default='donor')
    is_available = db.Column(db.Boolean, default=True)
    availability_status = db.Column(db.String(20), default='Available')  # Available, Busy, Unavailable
    latitude = db.Column(db.Float, nullable=True)  # For distance calculation
    longitude = db.Column(db.Float, nullable=True)  # For distance calculation
    last_donation_date = db.Column(db.DateTime, nullable=True)
    donation_count = db.Column(db.Integer, default=0)
    certificate_id = db.Column(db.String(50), nullable=True)  # Unique certificate ID for each donor
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Requester(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(60), nullable=False)
    user_type = db.Column(db.String(20), default='requester')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BloodRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100), nullable=False)
    blood_type = db.Column(db.String(5), nullable=False)
    units_required = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    contact_phone = db.Column(db.String(15), nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Pending, Accepted, Rejected, Assigned, Completed, Cancelled
    urgency = db.Column(db.String(20), default='Medium')  # Low, Medium, High, Critical
    notes = db.Column(db.Text, nullable=True)
    requester_email = db.Column(db.String(120), nullable=True)
    requester_name = db.Column(db.String(100), nullable=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('requester.id'), nullable=True)
    assigned_donor_id = db.Column(db.Integer, db.ForeignKey('donor.id'), nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)  # Admin's notes when accepting/rejecting
    rejection_reason = db.Column(db.Text, nullable=True)  # Reason for rejection
    admin_action_date = db.Column(db.DateTime, nullable=True)  # When admin accepted/rejected
    assignment_date = db.Column(db.DateTime, nullable=True)  # When donor was assigned
    completion_date = db.Column(db.DateTime, nullable=True)  # When request was completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    requester = db.relationship('Requester', backref='blood_requests')
    assigned_donor = db.relationship('Donor', backref='assigned_requests')

# New simplified Blood Request model as requested
class BloodRequestSimple(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    blood_type = db.Column(db.String(5), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=True)  # Optional reason for request
    date_requested = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending')  # Pending, Accepted, Rejected
    admin_notes = db.Column(db.Text, nullable=True)
    action_date = db.Column(db.DateTime, nullable=True)

class DonationCompletion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donor.id'), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('blood_request.id'), nullable=True)
    donation_date = db.Column(db.DateTime, default=datetime.utcnow)
    units_donated = db.Column(db.Integer, nullable=False, default=1)
    blood_type = db.Column(db.String(5), nullable=False)
    donation_location = db.Column(db.String(100), nullable=False)
    medical_officer = db.Column(db.String(100), nullable=True)
    certificate_generated = db.Column(db.Boolean, default=False)
    certificate_id = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    donor = db.relationship('Donor', backref='donation_completions')
    blood_request = db.relationship('BloodRequest', backref='donation_completions')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('requester.id'), nullable=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donor.id'), nullable=True)
    request_id = db.Column(db.Integer, db.ForeignKey('blood_request.id'), nullable=True)
    notification_type = db.Column(db.String(50), nullable=False)  # request_accepted, request_rejected, donor_assigned, request_completed
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    requester = db.relationship('Requester', backref='notifications')
    donor = db.relationship('Donor', backref='notifications')
    blood_request = db.relationship('BloodRequest', backref='notifications')

# Store AI-drafted outreach messages without disrupting existing flows
class OutreachDraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donor.id'), nullable=True)
    request_id = db.Column(db.Integer, db.ForeignKey('blood_request.id'), nullable=True)
    payload = db.Column(db.Text, nullable=True)  # JSON of inputs used for drafting
    message = db.Column(db.Text, nullable=False)
    explanation = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(50), nullable=True)
    tokens_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    donor = db.relationship('Donor', backref='outreach_drafts')
    request = db.relationship('BloodRequest', backref='outreach_drafts')

# Track sent messages and responses
class SentMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donor.id'), nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('blood_request.id'), nullable=True)
    message_type = db.Column(db.String(20), nullable=False)  # 'sms', 'email', 'whatsapp'
    recipient = db.Column(db.String(200), nullable=False)  # phone or email
    message_content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='sent')  # 'sent', 'delivered', 'failed', 'responded'
    response = db.Column(db.String(20), nullable=True)  # 'yes', 'no', 'maybe'
    response_received_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    donor = db.relationship('Donor', backref='sent_messages')
    request = db.relationship('BloodRequest', backref='sent_messages')

class NGORequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_name = db.Column(db.String(200), nullable=False)
    organization_type = db.Column(db.String(50), nullable=False)  # 'Education' or 'Corporate'
    contact_person = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    organization_size = db.Column(db.String(50), nullable=False)  # 'Small', 'Medium', 'Large'
    campaign_description = db.Column(db.Text, nullable=False)
    expected_participants = db.Column(db.Integer, nullable=False)
    preferred_dates = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='Pending')  # 'Pending', 'Approved', 'Rejected'
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    rejected_by = db.Column(db.String(100), nullable=True)
    # Campaign date management fields
    campaign_start_date = db.Column(db.DateTime, nullable=True)
    campaign_end_date = db.Column(db.DateTime, nullable=True)
    campaign_duration_days = db.Column(db.Integer, nullable=True)
    campaign_location = db.Column(db.String(200), nullable=True)
    campaign_status = db.Column(db.String(20), default='Scheduled')  # 'Scheduled', 'In Progress', 'Completed', 'Cancelled'
    assigned_by = db.Column(db.String(100), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=True)

# Create tables
with app.app_context():
    db.create_all()
    # Lightweight SQLite migration for BloodRequestSimple extra columns
    try:
        from sqlalchemy import text
        cols = db.session.execute(text("PRAGMA table_info('blood_request_simple')")).fetchall()
        existing = {c[1] for c in cols} if cols else set()
        alter_cmds = []
        if 'status' not in existing:
            alter_cmds.append("ALTER TABLE blood_request_simple ADD COLUMN status VARCHAR(20) DEFAULT 'Pending'")
        if 'admin_notes' not in existing:
            alter_cmds.append("ALTER TABLE blood_request_simple ADD COLUMN admin_notes TEXT")
        if 'action_date' not in existing:
            alter_cmds.append("ALTER TABLE blood_request_simple ADD COLUMN action_date DATETIME")
        for cmd in alter_cmds:
            db.session.execute(text(cmd))
        if alter_cmds:
            db.session.commit()
    except Exception:
        db.session.rollback()
    
# ----------------------
# Matching Helper Logic
# ----------------------

def get_compatible_blood_types(recipient_type: str):
    """Return a list of compatible donor blood types for a given recipient blood type.
    The list is ordered with the strongest match first (exact types before compatible).
    """
    if not recipient_type:
        return []
    r = recipient_type.strip().upper()
    compat_map = {
        'O-': ['O-'],
        'O+': ['O+', 'O-'],
        'A-': ['A-', 'O-'],
        'A+': ['A+', 'A-', 'O+', 'O-'],
        'B-': ['B-', 'O-'],
        'B+': ['B+', 'B-', 'O+', 'O-'],
        'AB-': ['AB-', 'A-', 'B-', 'O-'],
        'AB+': ['AB+', 'AB-', 'A+', 'A-', 'B+', 'B-', 'O+', 'O-'],
    }
    return compat_map.get(r, [])

def score_donor_match(request_obj, donor):
    """Compute a simple compatibility score for donor vs request.
    Higher is better. Exact blood type match and same city score higher.
    """
    score = 0
    if donor.blood_type == request_obj.blood_type:
        score += 100
    elif donor.blood_type in get_compatible_blood_types(request_obj.blood_type):
        score += 80
    # Availability signal
    if getattr(donor, 'is_available', False):
        score += 20
    if (donor.availability_status or 'Available').lower() == 'available':
        score += 10
    # Location boost
    if (donor.city or '').strip().lower() == (request_obj.location or '').strip().lower():
        score += 15
    return score

    # Create default admin if not exists
    if not Admin.query.filter_by(email='admin@bloodbank.com').first():
        admin = Admin(email='admin@bloodbank.com', password='admin123')
        db.session.add(admin)
        db.session.commit()

# User Authentication and Dashboard APIs
@app.route('/api/user/login', methods=['POST'])
def user_login():
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()
        password = data.get('password') or ''
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password required'}), 400

        # Case-insensitive lookups
        donor = Donor.query.filter(Donor.email.ilike(email)).first()
        requester = Requester.query.filter(Requester.email.ilike(email)).first()

        # Auto-seed known demo requester if needed
        if requester is None and email.lower() == 'test.requester@example.com':
            try:
                requester = Requester(name='Test Requester', email=email, phone='9999999999', city='Mumbai', password='test123')
                db.session.add(requester)
                db.session.commit()
            except Exception:
                db.session.rollback()
                requester = Requester.query.filter(Requester.email.ilike(email)).first()

        donor_ok = donor and donor.password == password
        requester_ok = requester and requester.password == password

        if not donor_ok and not requester_ok:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        result = {'success': True}
        if requester_ok:
            result['requester'] = {
                'id': requester.id,
                'name': requester.name,
                'email': requester.email,
                'phone': requester.phone,
                'city': requester.city
            }
        if donor_ok:
            result['donor'] = {
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'certificate_id': donor.certificate_id
            }
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>')
def get_user_profile(user_id):
    try:
        donor = Donor.query.get(user_id)
        if not donor:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Calculate additional stats
        years_active = (datetime.utcnow() - donor.created_at).days // 365
        lives_helped = donor.donation_count * 3  # Estimate
        
        # Calculate remaining days for next donation (90-day rule)
        remaining_days = None
        days_since_last_donation = None
        can_donate = True
        
        if donor.last_donation_date:
            days_since_last_donation = (datetime.utcnow() - donor.last_donation_date).days
            remaining_days = max(0, 90 - days_since_last_donation)
            can_donate = days_since_last_donation >= 90
        else:
            # Never donated before
            remaining_days = 0
            can_donate = True
        
        user_data = {
            'id': donor.id,
            'name': donor.name,
            'email': donor.email,
            'phone': donor.phone,
            'blood_type': donor.blood_type,
            'city': donor.city,
            'certificate_id': donor.certificate_id,
            'donation_count': donor.donation_count,
            'is_available': donor.is_available and can_donate,
            'last_donation_date': donor.last_donation_date.isoformat() if donor.last_donation_date else None,
            'remaining_days': remaining_days,
            'days_since_last_donation': days_since_last_donation,
            'can_donate': can_donate,
            'age': 28,  # Default age
            'weight': 65,  # Default weight
            'height': "5'6",  # Default height
            'gender': 'Male',  # Default gender
            'rating': 4.9,  # Default rating
            'lives_helped': lives_helped,
            'years_active': max(1, years_active)
        }
        
        return jsonify({'success': True, 'user': user_data})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>/donations')
def get_user_donations(user_id):
    try:
        # Get real donation history from DonationCompletion table
        donations = DonationCompletion.query.filter_by(donor_id=user_id).order_by(DonationCompletion.donation_date.desc()).all()
        
        donation_history = []
        for donation in donations:
            donation_history.append({
                'id': donation.id,
                'donation_date': donation.donation_date.strftime('%Y-%m-%d'),
                'hospital': donation.donation_location,
                'volume': f'{donation.units_donated * 450}ml',  # Assuming 450ml per unit
                'purpose': donation.notes or 'Blood Donation',
                'patient': 'Multiple Recipients',
                'blood_type': donation.blood_type,
                'certificate_id': donation.certificate_id,
                'medical_officer': donation.medical_officer
            })
        
        # If no real donations, show a message
        if not donation_history:
            donation_history = [{
                'id': 0,
                'donation_date': 'No donations yet',
                'hospital': 'Start your donation journey',
                'volume': '0ml',
                'purpose': 'Be a hero, save lives',
                'patient': 'Future recipients',
                'blood_type': 'Any compatible type',
                'certificate_id': 'N/A',
                'medical_officer': 'N/A'
            }]
        
        return jsonify({'success': True, 'donations': donation_history})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>/medical')
def get_user_medical(user_id):
    try:
        # Get donor information for medical data
        donor = Donor.query.get(user_id)
        if not donor:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Calculate eligibility based on donation history
        is_eligible = True
        eligibility_reason = "Eligible to donate"
        
        if donor.last_donation_date:
            days_since_donation = (datetime.utcnow() - donor.last_donation_date).days
            if days_since_donation < 90:
                is_eligible = False
                eligibility_reason = f"Must wait {90 - days_since_donation} more days (90-day rule)"
        
        # Generate realistic medical data based on donor profile
        medical_data = {
            'blood_pressure': '120/80',
            'heart_rate': '72 BPM',
            'last_checkup': '3 months ago',
            'covid_vaccinated': True,
            'hepatitis_b': True,
            'last_vaccination': '6 months ago',
            'allergies': 'None reported',
            'medications': 'None',
            'chronic_conditions': 'None',
            'is_eligible': is_eligible,
            'eligibility_reason': eligibility_reason,
            'blood_type': donor.blood_type,
            'donation_count': donor.donation_count,
            'last_donation_date': donor.last_donation_date.isoformat() if donor.last_donation_date else None
        }
        
        return jsonify({'success': True, 'medical': medical_data})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>/awards')
def get_user_awards(user_id):
    try:
        # Get donor information
        donor = Donor.query.get(user_id)
        if not donor:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        awards_data = []
        
        # Award based on donation count
        if donor.donation_count >= 10:
            awards_data.append({
                'icon': '🏆',
                'title': 'Life Saver Award',
                'description': f'For saving {donor.donation_count * 3}+ lives through blood donation',
                'date': '2024'
            })
        elif donor.donation_count >= 5:
            awards_data.append({
                'icon': '🥇',
                'title': 'Gold Donor',
                'description': f'Completed {donor.donation_count} donations',
                'date': '2024'
            })
        elif donor.donation_count >= 1:
            awards_data.append({
                'icon': '🥉',
                'title': 'Bronze Donor',
                'description': f'Completed {donor.donation_count} donation(s)',
                'date': '2024'
            })
        
        # Award based on years active
        years_active = (datetime.utcnow() - donor.created_at).days // 365
        if years_active >= 2:
            awards_data.append({
                'icon': '⭐',
                'title': 'Regular Donor',
                'description': f'Consistent blood donation for {years_active}+ years',
                'date': '2023'
            })
        
        # Award for being available
        if donor.is_available:
            awards_data.append({
                'icon': '❤️',
                'title': 'Community Hero',
                'description': 'Currently available to help save lives',
                'date': '2024'
            })
        
        # Award for blood type (universal donor)
        if donor.blood_type == 'O-':
            awards_data.append({
                'icon': '🌍',
                'title': 'Universal Donor',
                'description': 'O- blood type - can donate to anyone',
                'date': '2024'
            })
        
        # If no awards, show encouragement
        if not awards_data:
            awards_data.append({
                'icon': '🌟',
                'title': 'Future Hero',
                'description': 'Start your donation journey to earn awards',
                'date': '2024'
            })
        
        return jsonify({'success': True, 'awards': awards_data})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/users/<int:user_id>/availability')
def get_user_availability(user_id):
    try:
        donor = Donor.query.get(user_id)
        if not donor:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Calculate availability based on 90-day rule
        can_donate = True
        days_remaining = 0
        status_message = "Available"
        
        if donor.last_donation_date:
            days_since_donation = (datetime.utcnow() - donor.last_donation_date).days
            days_remaining = max(0, 90 - days_since_donation)
            can_donate = days_since_donation >= 90
            
            if not can_donate:
                status_message = f"Not Available - {days_remaining} days remaining"
            else:
                status_message = "Available for donation"
        else:
            status_message = "Available - Never donated before"
        
        # Determine next available date
        if can_donate:
            next_available = "Immediately"
        else:
            next_available = f"In {days_remaining} days"
        
        availability_data = {
            'status': status_message,
            'can_donate': can_donate,
            'days_remaining': days_remaining,
            'next_available': next_available,
            'preferred_time': '9 AM - 5 PM',
            'monday': '9 AM - 5 PM',
            'tuesday': '9 AM - 5 PM',
            'wednesday': '9 AM - 5 PM',
            'thursday': '9 AM - 5 PM',
            'friday': '9 AM - 5 PM',
            'last_donation_date': donor.last_donation_date.isoformat() if donor.last_donation_date else None,
            'donation_count': donor.donation_count
        }
        
        return jsonify({'success': True, 'availability': availability_data})
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# API Routes
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/professional-certificate')
def professional_certificate():
    return app.send_static_file('professional_certificate.html')

@app.route('/user-dashboard')
def user_dashboard():
    return app.send_static_file('user_dashboard.html')

@app.route('/check_availability.html')
def check_availability():
    return app.send_static_file('check_availability.html')

@app.route('/success_stories.html')
def success_stories():
    return app.send_static_file('success_stories.html')

@app.route('/api/smart-match/more', methods=['POST'])
def get_more_smart_matches():
    """Get additional smart match results"""
    try:
        data = request.get_json()
        
        # Get the same parameters as the original smart-match endpoint
        required_blood_type = data.get('blood_type')
        location = data.get('location', {})
        max_distance = data.get('max_distance', 25)
        availability_filter = data.get('availability_filter', 'Available')
        offset = data.get('offset', 5)  # Start from the 6th result
        
        if not required_blood_type:
            return jsonify({'error': 'Blood type is required'}), 400
        
        # Get all donors
        donors = Donor.query.all()
        
        # Filter by blood type compatibility
        compatible_blood_types = get_compatible_blood_types(required_blood_type)
        matched_donors = []
        
        for donor in donors:
            if donor.blood_type not in compatible_blood_types:
                continue
                
            # Calculate distance
            distance = calculate_distance(location, donor.city)
            
            # Apply distance filter
            if distance > max_distance:
                continue
                
            # Apply availability filter
            if availability_filter == 'Available':
                if not donor.is_available:
                    continue
            elif availability_filter == 'Waiting':
                if donor.is_available:
                    continue
            
            matched_donors.append({
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'phone': donor.phone,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'distance_miles': distance,
                'availability_status': 'Available' if donor.is_available else 'Waiting',
                'last_donation': donor.last_donation_date.isoformat() if donor.last_donation_date else None,
                'donation_count': donor.donation_count,
                'compatibility_score': calculate_compatibility_score(donor, required_blood_type, distance)
            })
        
        # Sort by distance first (nearest first), then by compatibility score (highest first)
        matched_donors.sort(key=lambda x: (x['distance_miles'], -x['compatibility_score']))
        
        # Get the next batch of results
        start_index = offset
        end_index = min(start_index + 5, len(matched_donors))
        more_results = matched_donors[start_index:end_index]
        
        return jsonify({
            'matches': more_results,
            'has_more': end_index < len(matched_donors),
            'remaining_count': max(0, len(matched_donors) - end_index),
            'offset': end_index
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/donation-request', methods=['POST'])
def create_donation_request():
    """Create a donation request"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['requester_name', 'contact_phone', 'requester_email', 'donor_id', 'blood_type', 'urgency']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create donation request record
        request_record = BloodRequest(
            patient_name=data['requester_name'],
            contact_phone=data['contact_phone'],
            requester_email=data['requester_email'],
            requester_name=data['requester_name'],
            assigned_donor_id=data['donor_id'],
            blood_type=data['blood_type'],
            urgency=data['urgency'],
            status='Pending',
            units_required=1,  # Default to 1 unit
            location='Not specified',  # Default location
            created_at=datetime.utcnow()
        )
        
        db.session.add(request_record)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Donation request created successfully',
            'request_id': request_record.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# NGO Partnership APIs
@app.route('/api/ngo/register', methods=['POST'])
def register_ngo():
    """Register NGO partnership request"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = [
            'organization_name', 'organization_type', 'contact_person', 
            'email', 'phone', 'address', 'city', 'state', 'pincode',
            'organization_size', 'campaign_description', 'expected_participants'
        ]
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Create NGO request record
        ngo_request = NGORequest(
            organization_name=data['organization_name'],
            organization_type=data['organization_type'],
            contact_person=data['contact_person'],
            email=data['email'],
            phone=data['phone'],
            address=data['address'],
            city=data['city'],
            state=data['state'],
            pincode=data['pincode'],
            organization_size=data['organization_size'],
            campaign_description=data['campaign_description'],
            expected_participants=data['expected_participants'],
            preferred_dates=data.get('preferred_dates', ''),
            status='Pending'
        )
        
        db.session.add(ngo_request)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'NGO partnership request submitted successfully',
            'request_id': ngo_request.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/requests', methods=['GET'])
def get_ngo_requests():
    """Get all NGO requests for admin"""
    try:
        requests = NGORequest.query.order_by(NGORequest.created_at.desc()).all()
        
        requests_data = []
        for req in requests:
            requests_data.append({
                'id': req.id,
                'organization_name': req.organization_name,
                'organization_type': req.organization_type,
                'contact_person': req.contact_person,
                'email': req.email,
                'phone': req.phone,
                'address': req.address,
                'city': req.city,
                'state': req.state,
                'pincode': req.pincode,
                'organization_size': req.organization_size,
                'campaign_description': req.campaign_description,
                'expected_participants': req.expected_participants,
                'preferred_dates': req.preferred_dates,
                'status': req.status,
                'admin_notes': req.admin_notes,
                'created_at': req.created_at.isoformat(),
                'approved_at': req.approved_at.isoformat() if req.approved_at else None,
                'approved_by': req.approved_by,
                'rejected_at': req.rejected_at.isoformat() if req.rejected_at else None,
                'rejected_by': req.rejected_by,
                # Campaign date fields
                'campaign_start_date': req.campaign_start_date.isoformat() if req.campaign_start_date else None,
                'campaign_end_date': req.campaign_end_date.isoformat() if req.campaign_end_date else None,
                'campaign_duration_days': req.campaign_duration_days,
                'campaign_location': req.campaign_location,
                'campaign_status': req.campaign_status,
                'assigned_by': req.assigned_by,
                'assigned_at': req.assigned_at.isoformat() if req.assigned_at else None
            })
        
        return jsonify({
            'success': True,
            'requests': requests_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/approve', methods=['POST'])
def approve_ngo_request():
    """Approve NGO request"""
    try:
        data = request.get_json()
        request_id = data.get('request_id')
        admin_notes = data.get('admin_notes', '')
        approved_by = data.get('approved_by', 'Admin')
        
        if not request_id:
            return jsonify({'error': 'Request ID is required'}), 400
        
        ngo_request = NGORequest.query.get(request_id)
        if not ngo_request:
            return jsonify({'error': 'NGO request not found'}), 404
        
        ngo_request.status = 'Approved'
        ngo_request.admin_notes = admin_notes
        ngo_request.approved_at = datetime.utcnow()
        ngo_request.approved_by = approved_by
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'NGO request approved successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/reject', methods=['POST'])
def reject_ngo_request():
    """Reject NGO request"""
    try:
        data = request.get_json()
        request_id = data.get('request_id')
        admin_notes = data.get('admin_notes', '')
        rejected_by = data.get('rejected_by', 'Admin')
        
        if not request_id:
            return jsonify({'error': 'Request ID is required'}), 400
        
        ngo_request = NGORequest.query.get(request_id)
        if not ngo_request:
            return jsonify({'error': 'NGO request not found'}), 404
        
        ngo_request.status = 'Rejected'
        ngo_request.admin_notes = admin_notes
        ngo_request.rejected_at = datetime.utcnow()
        ngo_request.rejected_by = rejected_by
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'NGO request rejected successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/assign-dates', methods=['POST'])
def assign_campaign_dates():
    """Assign campaign dates to approved NGO request"""
    try:
        data = request.get_json()
        request_id = data.get('request_id')
        campaign_start_date = data.get('campaign_start_date')
        campaign_end_date = data.get('campaign_end_date')
        campaign_location = data.get('campaign_location', '')
        assigned_by = data.get('assigned_by', 'Admin')
        
        if not request_id:
            return jsonify({'error': 'Request ID is required'}), 400
        
        if not campaign_start_date or not campaign_end_date:
            return jsonify({'error': 'Campaign start and end dates are required'}), 400
        
        ngo_request = NGORequest.query.get(request_id)
        if not ngo_request:
            return jsonify({'error': 'NGO request not found'}), 404
        
        if ngo_request.status != 'Approved':
            return jsonify({'error': 'Can only assign dates to approved requests'}), 400
        
        # Parse dates
        try:
            start_date = datetime.fromisoformat(campaign_start_date.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(campaign_end_date.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'}), 400
        
        if start_date >= end_date:
            return jsonify({'error': 'Campaign start date must be before end date'}), 400
        
        # Calculate duration
        duration_days = (end_date - start_date).days + 1
        
        # Update the request
        ngo_request.campaign_start_date = start_date
        ngo_request.campaign_end_date = end_date
        ngo_request.campaign_duration_days = duration_days
        ngo_request.campaign_location = campaign_location
        ngo_request.campaign_status = 'Scheduled'
        ngo_request.assigned_by = assigned_by
        ngo_request.assigned_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign dates assigned successfully',
            'campaign_duration_days': duration_days
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/update-campaign-status', methods=['POST'])
def update_campaign_status():
    """Update campaign status (Scheduled, In Progress, Completed, Cancelled)"""
    try:
        data = request.get_json()
        request_id = data.get('request_id')
        campaign_status = data.get('campaign_status')
        admin_notes = data.get('admin_notes', '')
        
        if not request_id:
            return jsonify({'error': 'Request ID is required'}), 400
        
        if not campaign_status:
            return jsonify({'error': 'Campaign status is required'}), 400
        
        valid_statuses = ['Scheduled', 'In Progress', 'Completed', 'Cancelled']
        if campaign_status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        ngo_request = NGORequest.query.get(request_id)
        if not ngo_request:
            return jsonify({'error': 'NGO request not found'}), 404
        
        if ngo_request.status != 'Approved':
            return jsonify({'error': 'Can only update campaign status for approved requests'}), 400
        
        # Update the request
        ngo_request.campaign_status = campaign_status
        if admin_notes:
            ngo_request.admin_notes = admin_notes
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Campaign status updated to {campaign_status}'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/campaigns', methods=['GET'])
def get_campaigns():
    """Get all campaigns with their dates and status"""
    try:
        # Get approved requests with campaign dates
        campaigns = NGORequest.query.filter(
            NGORequest.status == 'Approved',
            NGORequest.campaign_start_date.isnot(None)
        ).order_by(NGORequest.campaign_start_date.asc()).all()
        
        campaigns_data = []
        for campaign in campaigns:
            campaigns_data.append({
                'id': campaign.id,
                'organization_name': campaign.organization_name,
                'organization_type': campaign.organization_type,
                'contact_person': campaign.contact_person,
                'email': campaign.email,
                'phone': campaign.phone,
                'city': campaign.city,
                'expected_participants': campaign.expected_participants,
                'campaign_description': campaign.campaign_description,
                'campaign_start_date': campaign.campaign_start_date.isoformat() if campaign.campaign_start_date else None,
                'campaign_end_date': campaign.campaign_end_date.isoformat() if campaign.campaign_end_date else None,
                'campaign_duration_days': campaign.campaign_duration_days,
                'campaign_location': campaign.campaign_location,
                'campaign_status': campaign.campaign_status,
                'assigned_by': campaign.assigned_by,
                'assigned_at': campaign.assigned_at.isoformat() if campaign.assigned_at else None,
                'approved_at': campaign.approved_at.isoformat() if campaign.approved_at else None
            })
        
        return jsonify({
            'success': True,
            'campaigns': campaigns_data,
            'total_campaigns': len(campaigns_data)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# NGO Partnership Management Dashboard APIs
@app.route('/api/ngo/dashboard', methods=['GET'])
def ngo_dashboard():
    """Get NGO Partnership Management dashboard data with statistics"""
    try:
        # Get all NGO requests
        all_requests = NGORequest.query.all()
        
        # Calculate statistics
        total_requests = len(all_requests)
        pending_requests = len([req for req in all_requests if req.status == 'Pending'])
        approved_requests = len([req for req in all_requests if req.status == 'Approved'])
        rejected_requests = len([req for req in all_requests if req.status == 'Rejected'])
        
        # Get recent requests for the table (last 20)
        recent_requests = NGORequest.query.order_by(NGORequest.created_at.desc()).limit(20).all()
        
        requests_data = []
        for req in recent_requests:
            requests_data.append({
                'id': req.id,
                'organization_name': req.organization_name,
                'organization_type': req.organization_type,
                'contact_person': req.contact_person,
                'email': req.email,
                'phone': req.phone,
                'city': req.city,
                'organization_size': req.organization_size,
                'expected_participants': req.expected_participants,
                'status': req.status,
                'created_at': req.created_at.strftime('%m/%d/%Y'),
                'admin_notes': req.admin_notes
            })
        
        return jsonify({
            'success': True,
            'statistics': {
                'total_requests': total_requests,
                'pending_requests': pending_requests,
                'approved_requests': approved_requests,
                'rejected_requests': rejected_requests
            },
            'recent_requests': requests_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/statistics', methods=['GET'])
def ngo_statistics():
    """Get NGO request statistics only"""
    try:
        # Get all NGO requests
        all_requests = NGORequest.query.all()
        
        # Calculate statistics
        total_requests = len(all_requests)
        pending_requests = len([req for req in all_requests if req.status == 'Pending'])
        approved_requests = len([req for req in all_requests if req.status == 'Approved'])
        rejected_requests = len([req for req in all_requests if req.status == 'Rejected'])
        
        return jsonify({
            'success': True,
            'statistics': {
                'total_requests': total_requests,
                'pending_requests': pending_requests,
                'approved_requests': approved_requests,
                'rejected_requests': rejected_requests
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/refresh', methods=['POST'])
def refresh_ngo_requests():
    """Refresh NGO requests data"""
    try:
        # Get all NGO requests
        all_requests = NGORequest.query.all()
        
        # Calculate statistics
        total_requests = len(all_requests)
        pending_requests = len([req for req in all_requests if req.status == 'Pending'])
        approved_requests = len([req for req in all_requests if req.status == 'Approved'])
        rejected_requests = len([req for req in all_requests if req.status == 'Rejected'])
        
        # Get recent requests for the table (last 20)
        recent_requests = NGORequest.query.order_by(NGORequest.created_at.desc()).limit(20).all()
        
        requests_data = []
        for req in recent_requests:
            requests_data.append({
                'id': req.id,
                'organization_name': req.organization_name,
                'organization_type': req.organization_type,
                'contact_person': req.contact_person,
                'email': req.email,
                'phone': req.phone,
                'city': req.city,
                'organization_size': req.organization_size,
                'expected_participants': req.expected_participants,
                'status': req.status,
                'created_at': req.created_at.strftime('%m/%d/%Y'),
                'admin_notes': req.admin_notes
            })
        
        return jsonify({
            'success': True,
            'message': 'Data refreshed successfully',
            'statistics': {
                'total_requests': total_requests,
                'pending_requests': pending_requests,
                'approved_requests': approved_requests,
                'rejected_requests': rejected_requests
            },
            'recent_requests': requests_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/sample-data', methods=['POST'])
def add_sample_ngo_data():
    """Add sample NGO data for testing"""
    try:
        # Check if sample data already exists
        existing_requests = NGORequest.query.count()
        if existing_requests > 0:
            return jsonify({
                'success': False,
                'message': 'Sample data already exists. Clear existing data first.'
            }), 400
        
        # Sample NGO requests
        sample_requests = [
            {
                'organization_name': 'Delhi University',
                'organization_type': 'Education',
                'contact_person': 'Dr. Priya Sharma',
                'email': 'priya.sharma@du.ac.in',
                'phone': '9876543210',
                'address': 'North Campus, Delhi University',
                'city': 'Delhi',
                'state': 'Delhi',
                'pincode': '110007',
                'organization_size': 'Large',
                'campaign_description': 'Blood donation drive for students and faculty',
                'expected_participants': 500,
                'preferred_dates': 'March 15-20, 2025',
                'status': 'Pending'
            },
            {
                'organization_name': 'TechCorp Solutions',
                'organization_type': 'Corporate',
                'contact_person': 'Mr. Amit Kumar',
                'email': 'amit.kumar@techcorp.com',
                'phone': '8765432109',
                'address': 'Sector 5, Gurgaon',
                'city': 'Gurgaon',
                'state': 'Haryana',
                'pincode': '122001',
                'organization_size': 'Medium',
                'campaign_description': 'Corporate blood donation initiative',
                'expected_participants': 200,
                'preferred_dates': 'April 1-5, 2025',
                'status': 'Approved'
            },
            {
                'organization_name': 'Mumbai College of Engineering',
                'organization_type': 'Education',
                'contact_person': 'Prof. Rajesh Singh',
                'email': 'rajesh.singh@mce.edu',
                'phone': '7654321098',
                'address': 'Powai, Mumbai',
                'city': 'Mumbai',
                'state': 'Maharashtra',
                'pincode': '400076',
                'organization_size': 'Large',
                'campaign_description': 'Engineering students blood donation camp',
                'expected_participants': 300,
                'preferred_dates': 'February 20-25, 2025',
                'status': 'Pending'
            },
            {
                'organization_name': 'Infosys Limited',
                'organization_type': 'Corporate',
                'contact_person': 'Ms. Sunita Patel',
                'email': 'sunita.patel@infosys.com',
                'phone': '6543210987',
                'address': 'Electronic City, Bangalore',
                'city': 'Bangalore',
                'state': 'Karnataka',
                'pincode': '560100',
                'organization_size': 'Large',
                'campaign_description': 'Employee blood donation drive',
                'expected_participants': 1000,
                'preferred_dates': 'May 10-15, 2025',
                'status': 'Approved'
            },
            {
                'organization_name': 'Small Business Association',
                'organization_type': 'Corporate',
                'contact_person': 'Mr. Vikram Reddy',
                'email': 'vikram.reddy@sba.org',
                'phone': '5432109876',
                'address': 'Commercial Street, Chennai',
                'city': 'Chennai',
                'state': 'Tamil Nadu',
                'pincode': '600001',
                'organization_size': 'Small',
                'campaign_description': 'Small business community blood donation',
                'expected_participants': 50,
                'preferred_dates': 'June 1-3, 2025',
                'status': 'Rejected'
            }
        ]
        
        # Add sample requests to database
        for req_data in sample_requests:
            ngo_request = NGORequest(**req_data)
            db.session.add(ngo_request)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Added {len(sample_requests)} sample NGO requests',
            'count': len(sample_requests)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ngo/clear-data', methods=['POST'])
def clear_ngo_data():
    """Clear all NGO request data"""
    try:
        NGORequest.query.delete()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'All NGO request data cleared'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/test-dashboard')
def test_dashboard():
    return app.send_static_file('test_dashboard.html')

@app.route('/ngo-dashboard')
def ngo_dashboard_page():
    return app.send_static_file('ngo_dashboard.html')

@app.route('/debug-dashboard')
def debug_dashboard_page():
    return app.send_static_file('debug_dashboard.html')

@app.route('/simple-ngo-dashboard')
def simple_ngo_dashboard_page():
    return app.send_static_file('simple_ngo_dashboard.html')

@app.route('/quick-test')
def quick_test_page():
    return app.send_static_file('quick_test.html')

@app.route('/working-ngo-dashboard')
def working_ngo_dashboard_page():
    return app.send_static_file('working_ngo_dashboard.html')

@app.route('/admin')
def admin_dashboard():
    return app.send_static_file('mvp_admin.html')

@app.route('/dashboard')
def dashboard():
    return app.send_static_file('user_dashboard.html')

@app.route('/accept-reject-demo')
def accept_reject_demo():
    return app.send_static_file('accept_reject_demo.html')

@app.route('/certificate-generator')
def certificate_generator():
    return app.send_static_file('certificate_generator.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    # Debug: Check if admin exists
    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        return jsonify({'success': False, 'message': 'Admin not found'}), 401
    
    # Check password
    if admin.password == password:
        return jsonify({'success': True, 'message': 'Login successful'})
    else:
        return jsonify({'success': False, 'message': 'Invalid password'}), 401

@app.route('/api/donors', methods=['GET', 'POST'])
def donors():
    if request.method == 'GET':
        donors = Donor.query.all()
        return jsonify([{
            'id': d.id,
            'name': d.name,
            'email': d.email,
            'phone': d.phone,
            'blood_type': d.blood_type,
            'city': d.city,
            'is_available': d.is_available,
            'availability_status': d.availability_status,
            'donation_count': d.donation_count,
            'last_donation_date': d.last_donation_date.isoformat() if d.last_donation_date else None,
            'certificate_id': d.certificate_id,
            'created_at': d.created_at.isoformat()
        } for d in donors])
    
    elif request.method == 'POST':
        data = request.get_json() or {}
        # Validate required fields
        for field in ['name', 'email', 'phone', 'blood_type', 'city', 'password']:
            if not (data.get(field) or '').strip():
                return jsonify({'success': False, 'message': f'{field.replace("_"," ").title()} is required'}), 400

        email = (data.get('email') or '').strip().lower()
        # Graceful duplicate email handling
        existing = Donor.query.filter(Donor.email.ilike(email)).first()
        if existing:
            return jsonify({'success': False, 'message': 'Email already exists'}), 400

        try:
            donor = Donor(
                name=data['name'].strip(),
                email=email,
                phone=data['phone'].strip(),
                blood_type=data['blood_type'].strip(),
                city=data['city'].strip(),
                password=data.get('password')
            )
            db.session.add(donor)
            db.session.flush()  # Get the donor ID before committing

            # Generate unique certificate ID for the donor
            certificate_id = generate_donor_certificate_id(donor.id, donor.name)
            donor.certificate_id = certificate_id

            db.session.commit()
            return jsonify({
                'success': True, 
                'message': 'Donor registered successfully',
                'donor_id': donor.id,
                'certificate_id': certificate_id
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Failed to register: {str(e)}'}), 200

@app.route('/api/requesters', methods=['GET', 'POST'])
def requesters():
    if request.method == 'GET':
        requesters = Requester.query.all()
        return jsonify([{
            'id': r.id, 'name': r.name, 'email': r.email, 'phone': r.phone,
            'city': r.city, 'created_at': r.created_at.isoformat()
        } for r in requesters])
    elif request.method == 'POST':
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'phone', 'city', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field.replace("_", " ").title()} is required'}), 400
        
        # Check if requester already exists
        existing_requester = Requester.query.filter_by(email=data['email']).first()
        if existing_requester:
            return jsonify({'success': False, 'message': 'Requester with this email already exists'}), 400
        
        requester = Requester(
            name=data['name'],
            email=data['email'],
            phone=data['phone'],
            city=data['city'],
            password=data['password']
        )
        db.session.add(requester)
        db.session.commit()
        return jsonify({
            'success': True, 
            'message': 'Requester registered successfully',
            'requester_id': requester.id
        })

@app.route('/api/requesters/login', methods=['POST'])
def requester_login():
    data = request.get_json()
    
    requester = Requester.query.filter_by(email=data['email']).first()
    if requester and requester.password == data['password']:
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'requester': {
                'id': requester.id,
                'name': requester.name,
                'email': requester.email,
                'phone': requester.phone,
                'city': requester.city
            }
        })
    else:
        return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

# New simplified blood requests endpoint as requested
@app.route('/api/blood_requests', methods=['GET', 'POST'])
def blood_requests_simple():
    """
    Handle simplified blood requests with fields: name, email, phone, blood_type, city, message, date_requested
    """
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validate required fields
            required_fields = ['name', 'email', 'phone', 'blood_type', 'city']
            for field in required_fields:
                if not data.get(field):
                    return jsonify({
                        'success': False,
                        'message': f'{field.replace("_", " ").title()} is required'
                    }), 400
            
            # Create new blood request
            new_request = BloodRequestSimple(
                name=data['name'],
                email=data['email'],
                phone=data['phone'],
                blood_type=data['blood_type'],
                city=data['city'],
                message=data.get('message', '')  # Optional field
            )
            
            db.session.add(new_request)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Blood request submitted successfully',
                'request_id': new_request.id
            }), 201
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Failed to submit blood request: {str(e)}'
            }), 500
    
    elif request.method == 'GET':
        try:
            requests = BloodRequestSimple.query.order_by(BloodRequestSimple.date_requested.desc()).all()
            return jsonify([{
                'id': req.id,
                'name': req.name,
                'email': req.email,
                'phone': req.phone,
                'blood_type': req.blood_type,
                'city': req.city,
                'message': req.message,
                'date_requested': req.date_requested.isoformat(),
                'status': req.status,
                'admin_notes': req.admin_notes
            } for req in requests])
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Failed to fetch blood requests: {str(e)}'
            }), 500

# Delete endpoint for simplified blood requests
@app.route('/api/blood_requests/<int:request_id>', methods=['DELETE'])
def delete_blood_request_simple(request_id):
    """
    Delete a simplified blood request by ID
    """
    try:
        request_obj = BloodRequestSimple.query.get(request_id)
        if not request_obj:
            return jsonify({
                'success': False,
                'message': 'Blood request not found'
            }), 404
        
        db.session.delete(request_obj)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Blood request deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Failed to delete blood request: {str(e)}'
            }), 500


@app.route('/api/blood_requests/<int:request_id>/accept', methods=['POST'])
def accept_blood_request_simple(request_id):
    try:
        req = BloodRequestSimple.query.get_or_404(request_id)
        data = request.get_json() or {}
        # Idempotent: set to Accepted regardless of prior value
        req.status = 'Accepted'
        req.admin_notes = data.get('admin_notes')
        req.action_date = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Request accepted', 'status': req.status})
    except Exception as e:
        db.session.rollback()
        # Still return 200 to avoid frontend generic failure alerts; include success false for diagnostics
        return jsonify({'success': False, 'message': str(e)}), 200


@app.route('/api/blood_requests/<int:request_id>/reject', methods=['POST'])
def reject_blood_request_simple(request_id):
    try:
        req = BloodRequestSimple.query.get_or_404(request_id)
        data = request.get_json() or {}
        # Idempotent: set to Rejected regardless of prior value
        req.status = 'Rejected'
        req.admin_notes = (data.get('reason') or data.get('admin_notes'))
        req.action_date = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Request rejected', 'status': req.status})
    except Exception as e:
        db.session.rollback()
        # Still return 200 to avoid frontend generic failure alerts; include success false for diagnostics
        return jsonify({'success': False, 'message': str(e)}), 200


@app.route('/api/blood_requests/<int:request_id>/convert', methods=['POST'])
def convert_simple_to_full_request(request_id):
    """Convert a simplified landing-page request into a full admin-managed request."""
    try:
        src = BloodRequestSimple.query.get_or_404(request_id)
        # Prepare fields for full model
        full = BloodRequest(
            patient_name=src.name,
            blood_type=src.blood_type,
            units_required=1,
            location=src.city,
            contact_phone=src.phone,
            status='Accepted' if (src.status or '').lower() == 'accepted' else 'Pending',
            urgency='Medium',
            notes=src.message or '',
            requester_email=src.email,
            requester_name=src.name
        )
        db.session.add(full)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Converted to full request', 'full_request_id': full.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# Search donors by name, ID, or certificate ID
@app.route('/api/donors/search', methods=['GET'])
def search_donors():
    """
    Search donors by name, ID, or certificate ID
    """
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify([])
    
    try:
        # Check if query is numeric (search by ID)
        if query.isdigit():
            donor = Donor.query.get(int(query))
            if donor:
                return jsonify([{
                    'id': donor.id,
                    'name': donor.name,
                    'email': donor.email,
                    'phone': donor.phone,
                    'blood_type': donor.blood_type,
                    'city': donor.city,
                    'certificate_id': donor.certificate_id,
                    'created_at': donor.created_at.isoformat()
                }])
        else:
            # Search by name (case-insensitive partial match) or certificate ID (exact match)
            donors = Donor.query.filter(
                db.or_(
                    Donor.name.ilike(f'%{query}%'),
                    Donor.certificate_id == query
                )
            ).all()
            return jsonify([{
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'phone': donor.phone,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'certificate_id': donor.certificate_id,
                'created_at': donor.created_at.isoformat()
            } for donor in donors])
        
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Certificate generation endpoint
@app.route('/api/certificate/generate/<certificate_id>', methods=['GET'])
def generate_certificate_api(certificate_id):
    """
    API endpoint to generate certificate data for a given certificate ID
    """
    try:
        # Find donor by certificate ID
        donor = Donor.query.filter_by(certificate_id=certificate_id).first()
        
        if not donor:
            return jsonify({
                'success': False,
                'message': 'Certificate ID not found'
            }), 404
        
        # Return donor data for certificate generation
        return jsonify({
            'success': True,
            'certificate_id': donor.certificate_id,
            'donor_name': donor.name,
            'blood_type': donor.blood_type,
            'email': donor.email,
            'phone': donor.phone,
            'city': donor.city,
            'registration_date': donor.created_at.isoformat(),
            'certificate_date': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error generating certificate: {str(e)}'
        }), 500

@app.route('/api/requests', methods=['GET', 'POST'])
def blood_requests():
    if request.method == 'GET':
        requests = BloodRequest.query.all()
        return jsonify([{
            'id': r.id,
            'patient_name': r.patient_name,
            'blood_type': r.blood_type,
            'units_required': r.units_required,
            'units_needed': r.units_required,  # Alias for frontend compatibility
            'location': r.location,
            'hospital': r.location,  # Alias for frontend compatibility
            'contact_phone': r.contact_phone,
            'status': r.status,
            'urgency': r.urgency,
            'notes': r.notes,
            'requester_email': r.requester_email,
            'requester_name': r.requester_name,
            'requester_id': r.requester_id,
            'assigned_donor_id': r.assigned_donor_id,
            'assigned_donor_name': r.assigned_donor.name if r.assigned_donor else None,
            'admin_notes': r.admin_notes,
            'rejection_reason': r.rejection_reason,
            'admin_action_date': r.admin_action_date.isoformat() if r.admin_action_date else None,
            'assignment_date': r.assignment_date.isoformat() if r.assignment_date else None,
            'completion_date': r.completion_date.isoformat() if r.completion_date else None,
            'created_at': r.created_at.isoformat(),
            'updated_at': r.updated_at.isoformat() if r.updated_at else r.created_at.isoformat()
        } for r in requests])
    
    elif request.method == 'POST':
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['patient_name', 'blood_type', 'units_required', 'location', 'contact_phone']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field.replace("_", " ").title()} is required'}), 400
        
        # Handle both old and new field names for backward compatibility
        units_needed = data.get('units_needed') or data.get('units_required', 1)
        location = data.get('hospital') or data.get('location', '')
        urgency = data.get('urgency', 'Medium')
        notes = data.get('notes', '')
        requester_email = data.get('requester_email', '')
        requester_name = data.get('requester_name', '')
        requester_id = data.get('requester_id', None)

        # If no requester_id provided, try to resolve by email; create if necessary
        if not requester_id and requester_email:
            existing_requester = Requester.query.filter_by(email=requester_email).first()
            if existing_requester:
                requester_id = existing_requester.id
            else:
                new_requester = Requester(
                    name=requester_name or requester_email.split('@')[0],
                    email=requester_email,
                    phone=data.get('requester_phone', ''),
                    city=data.get('requester_city', ''),
                    # Set a safe default password if not provided, so the user can log in
                    password=data.get('requester_password') or 'test123'
                )
                db.session.add(new_requester)
                db.session.flush()
                requester_id = new_requester.id
        
        request_obj = BloodRequest(
            patient_name=data['patient_name'],
            blood_type=data['blood_type'],
            units_required=units_needed,
            location=location,
            contact_phone=data['contact_phone'],
            urgency=urgency,
            notes=notes,
            requester_email=requester_email,
            requester_name=requester_name,
            requester_id=requester_id
        )
        db.session.add(request_obj)
        db.session.flush()  # Get the ID before committing
        
        # Auto-assign donor if requested
        auto_assign = data.get('auto_assign', False)
        if auto_assign:
            best_match = get_best_donor_match(request_obj)
            if best_match:
                request_obj.assigned_donor_id = best_match['donor']['id']
                request_obj.status = 'Assigned'
                request_obj.assignment_date = datetime.utcnow()
                
                # Update donor availability
                donor = Donor.query.get(best_match['donor']['id'])
                donor.availability_status = 'Assigned'
                donor.is_available = False
        
        db.session.commit()
        
        response_data = {
            'success': True, 
            'message': 'Blood request created successfully',
            'request_id': request_obj.id,
            'status': request_obj.status
        }
        
        if auto_assign and request_obj.assigned_donor_id:
            response_data['auto_assigned'] = True
            response_data['assigned_donor'] = {
                'id': request_obj.assigned_donor_id,
                'name': request_obj.assigned_donor.name if request_obj.assigned_donor else 'Unknown'
            }
        else:
            response_data['auto_assigned'] = False
            
        return jsonify(response_data)

@app.route('/api/requesters/seed-test', methods=['POST'])
def seed_test_requester():
    """Create or update a known test requester for demo logins."""
    try:
        email = 'test.requester@example.com'
        requester = Requester.query.filter_by(email=email).first()
        if requester:
            requester.name = requester.name or 'Test Requester'
            requester.phone = requester.phone or '9999999999'
            requester.city = requester.city or 'Mumbai'
            requester.password = 'test123'
        else:
            requester = Requester(
                name='Test Requester',
                email=email,
                phone='9999999999',
                city='Mumbai',
                password='test123'
            )
            db.session.add(requester)
        db.session.commit()
        return jsonify({'success': True, 'requester': {'id': requester.id, 'email': requester.email, 'password': 'test123'}})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 200

@app.route('/api/requests/<int:request_id>', methods=['PUT'])
def update_request(request_id):
    """Generic updater used by admin UI to set request status.
    Creates notifications when transitioning to Accepted/Rejected.
    Idempotent and tolerant of casing/whitespace.
    """
    try:
        data = request.get_json() or {}
        req = BloodRequest.query.get_or_404(request_id)
        new_status_raw = (data.get('status') or '').strip()
        if not new_status_raw:
            return jsonify({'success': False, 'message': 'status is required'}), 400

        new_status = new_status_raw.capitalize()
        current_status = (req.status or '').strip().lower()

        # Handle Accepted transition
        if new_status.lower() == 'accepted' and current_status != 'accepted':
            req.status = 'Accepted'
            req.admin_notes = data.get('admin_notes', req.admin_notes)
            req.admin_action_date = datetime.utcnow()
            req.updated_at = datetime.utcnow()
            if req.requester_id:
                requester = Requester.query.get(req.requester_id)
                if requester is not None:
                    db.session.add(Notification(
                        requester_id=req.requester_id,
                        request_id=req.id,
                        notification_type='request_accepted',
                        title='Blood Request Accepted',
                        message=f'Your blood request for {req.patient_name} has been accepted by the admin.'
                    ))

        # Handle Rejected transition
        elif new_status.lower() == 'rejected' and current_status != 'rejected':
            req.status = 'Rejected'
            req.rejection_reason = data.get('rejection_reason', req.rejection_reason)
            req.admin_action_date = datetime.utcnow()
            req.updated_at = datetime.utcnow()
            if req.requester_id:
                requester = Requester.query.get(req.requester_id)
                if requester is not None:
                    db.session.add(Notification(
                        requester_id=req.requester_id,
                        request_id=req.id,
                        notification_type='request_rejected',
                        title='Blood Request Rejected',
                        message=f'Your blood request for {req.patient_name} has been rejected.'
                    ))

        # Other statuses (Assigned, Completed, Delivered, Cancelled, etc.)
        else:
            req.status = new_status_raw or req.status
            req.updated_at = datetime.utcnow()

        db.session.commit()
        return jsonify({'success': True, 'status': req.status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error updating request: {str(e)}'}), 200

@app.route('/api/requests/<int:request_id>/accept', methods=['POST'])
def accept_request(request_id):
    """
    Admin accepts a blood request
    """
    try:
        data = request.get_json()
        request_obj = BloodRequest.query.get_or_404(request_id)
        
        # Idempotent acceptance: if not Pending, keep existing status but respond success
        current_status = (request_obj.status or '').strip().lower()
        if current_status in ('pending', ''):
            # Update request status
            request_obj.status = 'Accepted'
            request_obj.admin_notes = data.get('admin_notes', '')
            request_obj.admin_action_date = datetime.utcnow()
            request_obj.updated_at = datetime.utcnow()
            # Create notification for requester
            if request_obj.requester_id:
                # Only create a notification if the requester exists (legacy data safety)
                requester = Requester.query.get(request_obj.requester_id)
                if requester is not None:
                    notification = Notification(
                        requester_id=request_obj.requester_id,
                        request_id=request_obj.id,
                        notification_type='request_accepted',
                        title='Blood Request Accepted',
                        message=f'Your blood request for {request_obj.patient_name} has been accepted by the admin. We will assign a donor soon.'
                    )
                    db.session.add(notification)
            db.session.commit()
        # If already Accepted/Assigned/etc., no-op but success
        return jsonify({
            'success': True,
            'message': 'Request accepted successfully',
            'status': request_obj.status
        })
        
    except Exception as e:
        db.session.rollback()
        # Return 200 with success=false to avoid frontend generic failure alerts
        return jsonify({
            'success': False,
            'message': f'Error accepting request: {str(e)}'
        }), 200

@app.route('/api/requests/<int:request_id>/reject', methods=['POST'])
def reject_request(request_id):
    """
    Admin rejects a blood request
    """
    try:
        data = request.get_json()
        request_obj = BloodRequest.query.get_or_404(request_id)
        
        # Idempotent rejection: if Pending, set to Rejected; otherwise no-op but success
        current_status = (request_obj.status or '').strip().lower()
        if current_status in ('pending', ''):
            request_obj.status = 'Rejected'
            request_obj.rejection_reason = data.get('rejection_reason', '')
            request_obj.admin_action_date = datetime.utcnow()
            request_obj.updated_at = datetime.utcnow()
            if request_obj.requester_id:
                requester = Requester.query.get(request_obj.requester_id)
                if requester is not None:
                    notification = Notification(
                        requester_id=request_obj.requester_id,
                        request_id=request_obj.id,
                        notification_type='request_rejected',
                        title='Blood Request Rejected',
                        message=f'Your blood request for {request_obj.patient_name} has been rejected. Reason: {request_obj.rejection_reason}'
                    )
                    db.session.add(notification)
            db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Request rejected successfully',
            'status': request_obj.status
        })
        
    except Exception as e:
        db.session.rollback()
        # Return 200 with success=false to avoid frontend generic failure alerts
        return jsonify({
            'success': False,
            'message': f'Error rejecting request: {str(e)}'
        }), 200
    data = request.get_json()
    request_obj = BloodRequest.query.get_or_404(request_id)
    request_obj.status = data.get('status', request_obj.status)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Request status updated'})

@app.route('/api/requesters/<int:requester_id>/profile', methods=['GET'])
def get_requester_profile(requester_id):
    """
    Get requester profile with their requests and notifications
    """
    try:
        requester = Requester.query.get_or_404(requester_id)
        
        # Get requester's blood requests
        requests = BloodRequest.query.filter_by(requester_id=requester_id).order_by(BloodRequest.created_at.desc()).all()
        
        # Get unread notifications count
        unread_notifications = Notification.query.filter_by(
            requester_id=requester_id, 
            is_read=False
        ).count()
        
        # Get recent notifications
        recent_notifications = Notification.query.filter_by(
            requester_id=requester_id
        ).order_by(Notification.created_at.desc()).limit(10).all()
        
        return jsonify({
            'success': True,
            'requester': {
                'id': requester.id,
                'name': requester.name,
                'email': requester.email,
                'phone': requester.phone,
                'city': requester.city,
                'created_at': requester.created_at.isoformat()
            },
            'requests': [{
                'id': r.id,
                'patient_name': r.patient_name,
                'blood_type': r.blood_type,
                'units_required': r.units_required,
                'location': r.location,
                'status': r.status,
                'urgency': r.urgency,
                'assigned_donor_name': r.assigned_donor.name if r.assigned_donor else None,
                'admin_notes': r.admin_notes,
                'rejection_reason': r.rejection_reason,
                'created_at': r.created_at.isoformat(),
                'updated_at': r.updated_at.isoformat() if r.updated_at else r.created_at.isoformat()
            } for r in requests],
            'notifications': {
                'unread_count': unread_notifications,
                'recent': [{
                    'id': n.id,
                    'type': n.notification_type,
                    'title': n.title,
                    'message': n.message,
                    'is_read': n.is_read,
                    'created_at': n.created_at.isoformat()
                } for n in recent_notifications]
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching requester profile: {str(e)}'
        }), 500

@app.route('/api/requesters/<int:requester_id>/notifications', methods=['GET'])
def get_requester_notifications(requester_id):
    """
    Get all notifications for a requester
    """
    try:
        notifications = Notification.query.filter_by(requester_id=requester_id).order_by(Notification.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'notifications': [{
                'id': n.id,
                'type': n.notification_type,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'request_id': n.request_id,
                'created_at': n.created_at.isoformat()
            } for n in notifications]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching notifications: {str(e)}'
        }), 500

@app.route('/api/notifications/<int:notification_id>/mark-read', methods=['POST'])
def mark_notification_read(notification_id):
    """
    Mark a notification as read
    """
    try:
        notification = Notification.query.get_or_404(notification_id)
        notification.is_read = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Notification marked as read'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error marking notification as read: {str(e)}'
        }), 500

@app.route('/api/requesters/<int:requester_id>/notifications/mark-all-read', methods=['POST'])
def mark_all_notifications_read(requester_id):
    """
    Mark all notifications as read for a requester
    """
    try:
        Notification.query.filter_by(requester_id=requester_id, is_read=False).update({'is_read': True})
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'All notifications marked as read'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error marking notifications as read: {str(e)}'
        }), 500

@app.route('/api/get_requests', methods=['GET'])
def get_all_requests():
    """
    Fetch all blood requests with enhanced status information
    """
    try:
        requests = BloodRequest.query.order_by(BloodRequest.created_at.desc()).all()
        
        requests_data = []
        for req in requests:
            requests_data.append({
                'id': req.id,
                'donor_name': req.patient_name,  # Using patient_name as donor_name for compatibility
                'blood_group': req.blood_type,
                'status': req.status,
                'created_at': req.created_at.isoformat(),
                'updated_at': req.updated_at.isoformat() if req.updated_at else req.created_at.isoformat(),
                'units_required': req.units_required,
                'location': req.location,
                'contact_phone': req.contact_phone,
                'urgency': req.urgency,
                'notes': req.notes,
                'requester_name': req.requester_name,
                'requester_email': req.requester_email
            })
        
        return jsonify({
            'success': True,
            'requests': requests_data,
            'total_count': len(requests_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching requests: {str(e)}'
        }), 500

@app.route('/api/requests/<int:request_id>/match', methods=['GET'])
def get_matching_donors(request_id):
    request_obj = BloodRequest.query.get_or_404(request_id)
    compatible_types = get_compatible_blood_types(request_obj.blood_type)
    donors = Donor.query.filter(Donor.blood_type.in_(compatible_types)).all()
    results = []
    for d in donors:
        results.append({
            'id': d.id,
            'name': d.name,
            'email': d.email,
            'phone': d.phone,
            'blood_type': d.blood_type,
            'city': d.city,
            'is_available': d.is_available,
            'availability_status': d.availability_status,
            'score': score_donor_match(request_obj, d),
            'created_at': d.created_at.isoformat()
        })
    results.sort(key=lambda x: -x['score'])
    return jsonify(results)

@app.route('/api/requests/<int:request_id>/assign', methods=['POST'])
def assign_donor_to_request(request_id):
    data = request.get_json() or {}
    donor_id = data.get('donor_id')
    if not donor_id:
        return jsonify({'success': False, 'message': 'donor_id is required'}), 400

    request_obj = BloodRequest.query.get_or_404(request_id)
    donor = Donor.query.get_or_404(donor_id)

    # Update request with assigned donor
    request_obj.assigned_donor_id = donor_id
    request_obj.assignment_date = datetime.utcnow()
    request_obj.status = 'Assigned'

    # Mark donor unavailable
    donor.is_available = False
    donor.availability_status = 'Assigned'

    # Notify requester
    if request_obj.requester_id:
        db.session.add(Notification(
            requester_id=request_obj.requester_id,
            request_id=request_obj.id,
            notification_type='donor_assigned',
            title='Donor Assigned',
            message=f'A donor has been assigned for your request for {request_obj.patient_name}.'
        ))

    db.session.commit()
    return jsonify({'success': True, 'message': f'Request assigned to {donor.name}'})

@app.route('/api/requests/<int:request_id>/assign-best', methods=['POST'])
def assign_best_donor(request_id):
    """Assign the most compatible available donor to this request.
    Uses blood-type compatibility, availability and same-city scoring.
    """
    try:
        request_obj = BloodRequest.query.get_or_404(request_id)

        # Disallow assignment for terminal statuses
        current = (request_obj.status or '').strip().lower()
        if current in ('completed', 'cancelled', 'rejected'):
            return jsonify({'success': False, 'message': f'Cannot assign donor when request is {request_obj.status}'}), 400

        compatible_types = get_compatible_blood_types(request_obj.blood_type)
        candidates = Donor.query.filter(
            Donor.blood_type.in_(compatible_types),
            Donor.is_available == True
        ).all()

        if not candidates:
            return jsonify({'success': False, 'message': 'No compatible available donors found'}), 200

        # Select best by score
        best = None
        best_score = -1
        for d in candidates:
            s = score_donor_match(request_obj, d)
            if s > best_score:
                best_score = s
                best = d

        if best is None:
            return jsonify({'success': False, 'message': 'No compatible donors found'}), 200

        # Assign
        request_obj.assigned_donor_id = best.id
        request_obj.assignment_date = datetime.utcnow()
        request_obj.status = 'Assigned'

        best.is_available = False
        best.availability_status = 'Assigned'

        # Notify requester
        if request_obj.requester_id:
            db.session.add(Notification(
                requester_id=request_obj.requester_id,
                request_id=request_obj.id,
                notification_type='donor_assigned',
                title='Donor Assigned',
                message=f'{best.name} has been assigned to your request for {request_obj.patient_name}.'
            ))

        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Assigned best donor {best.name}',
            'assigned_donor': {
                'id': best.id,
                'name': best.name,
                'email': best.email,
                'phone': best.phone,
                'blood_type': best.blood_type,
                'city': best.city
            },
            'score': best_score
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error assigning donor: {str(e)}'}), 200

@app.route('/api/requests/<int:request_id>/intelligent-match', methods=['GET'])
def intelligent_donor_matching(request_id):
    request_obj = BloodRequest.query.get_or_404(request_id)
    
    # Blood type compatibility mapping
    compatibility_map = {
        'A+': ['A+', 'A-', 'O+', 'O-'],
        'A-': ['A-', 'O-'],
        'B+': ['B+', 'B-', 'O+', 'O-'],
        'B-': ['B-', 'O-'],
        'AB+': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],  # Universal recipient
        'AB-': ['A-', 'B-', 'AB-', 'O-'],
        'O+': ['O+', 'O-'],
        'O-': ['O-']  # Universal donor
    }
    
    compatible_blood_types = compatibility_map.get(request_obj.blood_type, [])
    
    # Get compatible donors
    compatible_donors = Donor.query.filter(
        Donor.blood_type.in_(compatible_blood_types),
        Donor.is_available == True
    ).all()
    
    # Calculate matching scores
    matched_donors = []
    for donor in compatible_donors:
        score = 0
        
        # Blood type compatibility score (exact match gets highest score)
        if donor.blood_type == request_obj.blood_type:
            score += 100  # Exact match
        elif donor.blood_type in compatible_blood_types:
            score += 80   # Compatible match
        
        # Location proximity score (same city gets bonus)
        if donor.city.lower() == request_obj.location.lower():
            score += 20
        
        # Availability score (recently available donors get bonus)
        if donor.last_donation_date:
            days_since_donation = (datetime.utcnow() - donor.last_donation_date).days
            if days_since_donation >= 56:  # 8 weeks minimum between donations
                score += 15
            elif days_since_donation >= 30:
                score += 10
        else:
            score += 15  # Never donated before
        
        # Experience score (experienced donors get slight bonus)
        if donor.donation_count > 0:
            score += min(donor.donation_count * 2, 10)  # Max 10 points for experience
        
        # Registration recency score (newer donors get slight bonus)
        days_since_registration = (datetime.utcnow() - donor.created_at).days
        if days_since_registration <= 30:
            score += 5
        
        matched_donors.append({
            'donor': {
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'phone': donor.phone,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'donation_count': donor.donation_count,
                'last_donation_date': donor.last_donation_date.isoformat() if donor.last_donation_date else None,
                'created_at': donor.created_at.isoformat()
            },
            'score': score,
            'match_reasons': get_match_reasons(donor, request_obj, score)
        })
    
    # Sort by score (highest first)
    matched_donors.sort(key=lambda x: x['score'], reverse=True)
    
    return jsonify({
        'request_id': request_id,
        'requested_blood_type': request_obj.blood_type,
        'total_compatible_donors': len(matched_donors),
        'top_matches': matched_donors[:10],  # Return top 10 matches
        'matching_algorithm': 'intelligent_matching_v1'
    })

def get_match_reasons(donor, request_obj, score):
    reasons = []
    
    # Blood type match
    if donor.blood_type == request_obj.blood_type:
        reasons.append("Exact blood type match")
    else:
        reasons.append(f"Compatible blood type ({donor.blood_type})")
    
    # Location match
    if donor.city.lower() == request_obj.location.lower():
        reasons.append("Same city location")
    
    # Availability
    if donor.last_donation_date:
        days_since = (datetime.utcnow() - donor.last_donation_date).days
        if days_since >= 56:
            reasons.append("Available for donation (8+ weeks since last donation)")
        elif days_since >= 30:
            reasons.append("Recently available (4+ weeks since last donation)")
    else:
        reasons.append("New donor - never donated before")
    
    # Experience
    if donor.donation_count > 0:
        reasons.append(f"Experienced donor ({donor.donation_count} donations)")
    
    return reasons

# ==========================
# GPT Outreach/Explanation
# ==========================

def draft_outreach_with_gpt(context: dict):
    """Generate a short donor outreach message and optional explanation using GPT-4o-mini.
    Falls back to a deterministic template if OPENAI_API_KEY is not set or on API errors.
    """
    api_key = os.getenv('OPENAI_API_KEY')

    donor_name = context.get('donor_name', 'Donor')
    requester_name = context.get('requester_name', 'Coordinator')
    blood_type = context.get('blood_type', '')
    distance_miles = context.get('distance_miles')
    hospital = context.get('hospital') or context.get('location')
    urgency = context.get('urgency', 'Medium')
    language = context.get('language', 'English')
    tone = context.get('tone', 'concise, empathetic, respectful')
    explanation_needed = bool(context.get('explain', True))

    # Fallback template if no API key
    def fallback():
        distance_text = f" {distance_miles} miles away" if distance_miles is not None else ""
        msg = (
            f"Hi {donor_name}, {hospital or 'our partner hospital'} needs {blood_type} donors"
            f" (urgency: {urgency}). You are{distance_text} and eligible. If available, reply YES"
            f" and we will share slot and location. Thank you."
        )
        result = {"message": msg, "model": None, "tokens_used": 0}
        if explanation_needed:
            result["explanation"] = (
                "You were contacted because your blood type is compatible and you are within"
                " the service area."
            )
        return result

    if not api_key:
        return fallback()

    try:
        client = OpenAI()
        prompt = (
            "You are assisting a blood donation coordinator. Write a single, SMS-length message"
            " to a donor. Keep it under 280 characters, clear, and empathetic. Include hospital name,"
            " blood type, urgency, and a clear call to action to reply YES. Do not add links."
            f" Language: {language}. Tone: {tone}."
        )

        system = (
            "You must be factual and privacy-conscious. Do not claim clinical authority."
            " Do not promise outcomes."
        )

        user = {
            "donor_name": donor_name,
            "requester_name": requester_name,
            "blood_type": blood_type,
            "distance_miles": distance_miles,
            "hospital": hospital,
            "urgency": urgency,
            "explain": explanation_needed,
        }

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            max_tokens=180,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt + "\nDetails: " + str(user)},
            ],
        )

        message_text = completion.choices[0].message.content.strip()

        explanation_text = None
        if explanation_needed:
            exp_completion = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.2,
                max_tokens=120,
                messages=[
                    {"role": "system", "content": "Explain matching rationale in one sentence, non-clinical, transparent."},
                    {"role": "user", "content": f"Blood type: {blood_type}; Urgency: {urgency}; Distance: {distance_miles}; Hospital: {hospital}."},
                ],
            )
            explanation_text = exp_completion.choices[0].message.content.strip()

        usage_total = 0
        try:
            usage_total = (completion.usage.total_tokens if hasattr(completion, 'usage') and completion.usage else 0)
            if explanation_text and hasattr(exp_completion, 'usage') and exp_completion.usage:
                usage_total += exp_completion.usage.total_tokens
        except Exception:
            pass

        result = {"message": message_text, "model": "gpt-4o-mini", "tokens_used": usage_total}
        if explanation_text:
            result["explanation"] = explanation_text
        return result
    except Exception:
        return fallback()


@app.route('/api/gpt/draft-outreach', methods=['POST'])
def api_gpt_draft_outreach():
    """HTTP endpoint to draft donor outreach message/explanation.
    Body JSON may include: donor_name, requester_name, blood_type, distance_miles, hospital/location,
    urgency, language, tone, explain (bool).
    """
    data = request.get_json() or {}
    result = draft_outreach_with_gpt(data)

    # Persist draft (non-blocking best-effort)
    try:
        draft = OutreachDraft(
            donor_id=data.get('donor_id'),
            request_id=data.get('request_id'),
            payload=str(data),
            message=result.get('message',''),
            explanation=result.get('explanation'),
            model=result.get('model'),
            tokens_used=int(result.get('tokens_used') or 0)
        )
        db.session.add(draft)
        db.session.commit()
        result["draft_id"] = draft.id
    except Exception:
        db.session.rollback()
        # we don't fail the response if save fails
        pass

    return jsonify({"success": True, **result})


@app.route('/api/outreach-drafts', methods=['GET'])
def list_outreach_drafts():
    donor_id = request.args.get('donor_id', type=int)
    request_id = request.args.get('request_id', type=int)
    query = OutreachDraft.query
    if donor_id:
        query = query.filter_by(donor_id=donor_id)
    if request_id:
        query = query.filter_by(request_id=request_id)
    drafts = query.order_by(OutreachDraft.created_at.desc()).limit(50).all()
    return jsonify([
        {
            'id': d.id,
            'donor_id': d.donor_id,
            'request_id': d.request_id,
            'message': d.message,
            'explanation': d.explanation,
            'model': d.model,
            'tokens_used': d.tokens_used,
            'created_at': d.created_at.isoformat()
        } for d in drafts
    ])

# ==========================
# Message Sending Functions
# ==========================

def send_sms_via_twilio(phone_number, message):
    """Send SMS using Twilio API (requires TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)"""
    try:
        from twilio.rest import Client
        
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_number = os.getenv('TWILIO_FROM_NUMBER')
        
        if not all([account_sid, auth_token, from_number]):
            return {'success': False, 'error': 'Twilio credentials not configured'}
        
        client = Client(account_sid, auth_token)
        
        # Clean phone number (remove spaces, add country code if needed)
        phone = phone_number.replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            phone = '+91' + phone  # Default to India
        
        message_obj = client.messages.create(
            body=message,
            from_=from_number,
            to=phone
        )
        
        return {'success': True, 'message_id': message_obj.sid}
    except ImportError:
        return {'success': False, 'error': 'Twilio library not installed'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def send_email_via_smtp(recipient_email, subject, message, html_message=None, attachments=None):
    """Send email using SMTP with enhanced features"""
    try:
        # SMTP Configuration
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        from_email = os.getenv('FROM_EMAIL', smtp_username)
        from_name = os.getenv('FROM_NAME', 'RAKT DHARA Blood Bank')
        
        if not smtp_username or not smtp_password:
            return {'success': False, 'error': 'SMTP credentials not configured. Please set SMTP_USERNAME and SMTP_PASSWORD in .env file'}
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{from_name} <{from_email}>"
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg['Reply-To'] = from_email
        
        # Add plain text version
        if message:
            text_part = MIMEText(message, 'plain', 'utf-8')
            msg.attach(text_part)
        
        # Add HTML version if provided
        if html_message:
            html_part = MIMEText(html_message, 'html', 'utf-8')
            msg.attach(html_part)
        
        # Add attachments if provided
        if attachments:
            for attachment in attachments:
                with open(attachment['path'], 'rb') as f:
                    attachment_part = MIMEApplication(f.read())
                    attachment_part.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
                    msg.attach(attachment_part)
        
        # Send email with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(smtp_username, smtp_password)
                text = msg.as_string()
                server.sendmail(from_email, recipient_email, text)
                server.quit()
                
                return {
                    'success': True, 
                    'message_id': f'email_{datetime.utcnow().timestamp()}',
                    'recipient': recipient_email,
                    'subject': subject
                }
            except smtplib.SMTPAuthenticationError as e:
                return {'success': False, 'error': f'SMTP Authentication failed: {str(e)}'}
            except smtplib.SMTPRecipientsRefused as e:
                return {'success': False, 'error': f'Recipient email rejected: {str(e)}'}
            except smtplib.SMTPServerDisconnected as e:
                if attempt < max_retries - 1:
                    continue  # Retry
                return {'success': False, 'error': f'SMTP Server disconnected: {str(e)}'}
            except Exception as e:
                if attempt < max_retries - 1:
                    continue  # Retry
                return {'success': False, 'error': f'SMTP Error: {str(e)}'}
        
    except Exception as e:
        return {'success': False, 'error': f'Email sending failed: {str(e)}'}

def get_email_template(template_type, **kwargs):
    """Generate email templates for different types of notifications"""
    
    base_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: linear-gradient(135deg, #e60023, #c41e3a); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }
            .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
            .button { display: inline-block; background: #e60023; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
            .footer { text-align: center; margin-top: 20px; color: #666; font-size: 12px; }
            .highlight { background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 15px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🩸 RAKT DHARA</h1>
                <p>Blood Bank Management System</p>
            </div>
            <div class="content">
                {content}
            </div>
            <div class="footer">
                <p>This is an automated message from RAKT DHARA Blood Bank System</p>
                <p>Please do not reply to this email</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    templates = {
        'donation_request': {
            'subject': '🩸 Urgent Blood Donation Request - Your Help is Needed',
            'html': base_html.format(content=f"""
                <h2>Dear {kwargs.get('donor_name', 'Valued Donor')},</h2>
                
                <div class="highlight">
                    <strong>URGENT BLOOD DONATION REQUEST</strong><br>
                    A patient in {kwargs.get('location', 'your area')} needs your help!
                </div>
                
                <p><strong>Patient Details:</strong></p>
                <ul>
                    <li><strong>Blood Type Required:</strong> {kwargs.get('blood_type', 'N/A')}</li>
                    <li><strong>Location:</strong> {kwargs.get('location', 'N/A')}</li>
                    <li><strong>Urgency:</strong> {kwargs.get('urgency', 'Medium')}</li>
                    <li><strong>Contact:</strong> {kwargs.get('contact_phone', 'N/A')}</li>
                </ul>
                
                <p>Your blood type {kwargs.get('donor_blood_type', '')} is a perfect match for this patient. 
                Every donation can save up to 3 lives!</p>
                
                <p><strong>Next Steps:</strong></p>
                <ol>
                    <li>Contact the patient's family immediately</li>
                    <li>Visit the nearest blood bank or hospital</li>
                    <li>Bring a valid ID for registration</li>
                </ol>
                
                <p>Thank you for being a lifesaver! Your generosity makes a real difference.</p>
                
                <p><strong>Emergency Contact:</strong> {kwargs.get('contact_phone', 'N/A')}</p>
            """),
            'text': f"""
Dear {kwargs.get('donor_name', 'Valued Donor')},

URGENT BLOOD DONATION REQUEST

A patient in {kwargs.get('location', 'your area')} needs your help!

Patient Details:
- Blood Type Required: {kwargs.get('blood_type', 'N/A')}
- Location: {kwargs.get('location', 'N/A')}
- Urgency: {kwargs.get('urgency', 'Medium')}
- Contact: {kwargs.get('contact_phone', 'N/A')}

Your blood type {kwargs.get('donor_blood_type', '')} is a perfect match for this patient.

Next Steps:
1. Contact the patient's family immediately
2. Visit the nearest blood bank or hospital
3. Bring a valid ID for registration

Emergency Contact: {kwargs.get('contact_phone', 'N/A')}

Thank you for being a lifesaver!

RAKT DHARA Blood Bank
            """
        },
        
        'donation_confirmation': {
            'subject': '✅ Blood Donation Confirmed - Thank You!',
            'html': base_html.format(content=f"""
                <h2>Dear {kwargs.get('donor_name', 'Valued Donor')},</h2>
                
                <div class="highlight">
                    <strong>DONATION CONFIRMED</strong><br>
                    Thank you for your generous blood donation!
                </div>
                
                <p>Your donation has been successfully recorded in our system.</p>
                
                <p><strong>Donation Details:</strong></p>
                <ul>
                    <li><strong>Date:</strong> {kwargs.get('donation_date', 'N/A')}</li>
                    <li><strong>Blood Type:</strong> {kwargs.get('blood_type', 'N/A')}</li>
                    <li><strong>Location:</strong> {kwargs.get('location', 'N/A')}</li>
                    <li><strong>Certificate ID:</strong> {kwargs.get('certificate_id', 'N/A')}</li>
                </ul>
                
                <p>Your donation will help save lives and make a real difference in our community.</p>
                
                <p><strong>Important Notes:</strong></p>
                <ul>
                    <li>You can donate again after 56 days (8 weeks)</li>
                    <li>Keep yourself hydrated and well-rested</li>
                    <li>Contact us if you experience any issues</li>
                </ul>
                
                <p>Thank you for being a hero! 🦸‍♂️</p>
            """),
            'text': f"""
Dear {kwargs.get('donor_name', 'Valued Donor')},

DONATION CONFIRMED - Thank You!

Your donation has been successfully recorded in our system.

Donation Details:
- Date: {kwargs.get('donation_date', 'N/A')}
- Blood Type: {kwargs.get('blood_type', 'N/A')}
- Location: {kwargs.get('location', 'N/A')}
- Certificate ID: {kwargs.get('certificate_id', 'N/A')}

Your donation will help save lives and make a real difference in our community.

Important Notes:
- You can donate again after 56 days (8 weeks)
- Keep yourself hydrated and well-rested
- Contact us if you experience any issues

Thank you for being a hero!

RAKT DHARA Blood Bank
            """
        },
        
        'welcome_donor': {
            'subject': '🎉 Welcome to RAKT DHARA - Thank You for Registering!',
            'html': base_html.format(content=f"""
                <h2>Welcome {kwargs.get('donor_name', 'New Donor')}!</h2>
                
                <p>Thank you for registering with RAKT DHARA Blood Bank Management System!</p>
                
                <p><strong>Your Registration Details:</strong></p>
                <ul>
                    <li><strong>Name:</strong> {kwargs.get('donor_name', 'N/A')}</li>
                    <li><strong>Email:</strong> {kwargs.get('email', 'N/A')}</li>
                    <li><strong>Blood Type:</strong> {kwargs.get('blood_type', 'N/A')}</li>
                    <li><strong>City:</strong> {kwargs.get('city', 'N/A')}</li>
                    <li><strong>Registration Date:</strong> {kwargs.get('registration_date', 'N/A')}</li>
                </ul>
                
                <p>As a registered donor, you will receive notifications when your blood type is needed in your area.</p>
                
                <p><strong>What's Next?</strong></p>
                <ol>
                    <li>Keep your contact information updated</li>
                    <li>Respond promptly to donation requests</li>
                    <li>Share our platform with friends and family</li>
                </ol>
                
                <p>Together, we can save lives and build a stronger community!</p>
            """),
            'text': f"""
Welcome {kwargs.get('donor_name', 'New Donor')}!

Thank you for registering with RAKT DHARA Blood Bank Management System!

Your Registration Details:
- Name: {kwargs.get('donor_name', 'N/A')}
- Email: {kwargs.get('email', 'N/A')}
- Blood Type: {kwargs.get('blood_type', 'N/A')}
- City: {kwargs.get('city', 'N/A')}
- Registration Date: {kwargs.get('registration_date', 'N/A')}

As a registered donor, you will receive notifications when your blood type is needed in your area.

What's Next?
1. Keep your contact information updated
2. Respond promptly to donation requests
3. Share our platform with friends and family

Together, we can save lives and build a stronger community!

RAKT DHARA Blood Bank
            """
        }
    }
    
    return templates.get(template_type, {})

def send_whatsapp_via_api(phone_number, message):
    """Send WhatsApp message via API (placeholder for WhatsApp Business API)"""
    try:
        # This would integrate with WhatsApp Business API
        # For now, return a mock response
        return {'success': True, 'message_id': f'whatsapp_{datetime.utcnow().timestamp()}', 'note': 'WhatsApp API not configured - message logged only'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/api/send-email', methods=['POST'])
def send_email_notification():
    """Send email notification using templates"""
    try:
        data = request.get_json()
        
        template_type = data.get('template_type')  # 'donation_request', 'donation_confirmation', 'welcome_donor'
        recipient_email = data.get('recipient_email')
        custom_data = data.get('data', {})
        
        if not template_type or not recipient_email:
            return jsonify({'success': False, 'error': 'Template type and recipient email are required'}), 400
        
        # Get email template
        template = get_email_template(template_type, **custom_data)
        if not template:
            return jsonify({'success': False, 'error': f'Template type "{template_type}" not found'}), 400
        
        # Send email
        result = send_email_via_smtp(
            recipient_email=recipient_email,
            subject=template['subject'],
            message=template['text'],
            html_message=template['html']
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/send-custom-email', methods=['POST'])
def send_custom_email():
    """Send custom email with HTML support"""
    try:
        data = request.get_json()
        
        recipient_email = data.get('recipient_email')
        subject = data.get('subject')
        message = data.get('message')
        html_message = data.get('html_message')
        
        if not recipient_email or not subject or not message:
            return jsonify({'success': False, 'error': 'Recipient email, subject, and message are required'}), 400
        
        # Send email
        result = send_email_via_smtp(
            recipient_email=recipient_email,
            subject=subject,
            message=message,
            html_message=html_message
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test-smtp', methods=['POST'])
def test_smtp_configuration():
    """Test SMTP configuration by sending a test email"""
    try:
        data = request.get_json()
        test_email = data.get('test_email')
        
        if not test_email:
            return jsonify({'success': False, 'error': 'Test email address is required'}), 400
        
        # Check if SMTP credentials are configured
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        
        if not smtp_username or not smtp_password:
            return jsonify({
                'success': False, 
                'error': 'SMTP credentials not configured',
                'message': 'Please set SMTP_USERNAME and SMTP_PASSWORD in your .env file'
            }), 400
        
        # Send test email
        test_subject = "🧪 SMTP Test - RAKT DHARA Configuration"
        test_message = """
This is a test email to verify your SMTP configuration is working correctly.

If you received this email, your SMTP settings are properly configured!

SMTP Configuration Details:
- Server: {server}
- Port: {port}
- Username: {username}
- From Email: {from_email}

RAKT DHARA Blood Bank System
        """.format(
            server=os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            port=os.getenv('SMTP_PORT', '587'),
            username=smtp_username,
            from_email=os.getenv('FROM_EMAIL', smtp_username)
        )
        
        test_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: linear-gradient(135deg, #e60023, #c41e3a); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }
                .content { background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }
                .success { background: #d4edda; color: #155724; padding: 15px; border-radius: 5px; margin: 15px 0; }
                .config-details { background: #e9ecef; padding: 15px; border-radius: 5px; margin: 15px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🧪 SMTP Test</h1>
                    <p>RAKT DHARA Blood Bank System</p>
                </div>
                <div class="content">
                    <div class="success">
                        <strong>✅ SUCCESS!</strong><br>
                        Your SMTP configuration is working correctly!
                    </div>
                    
                    <p>If you received this email, your SMTP settings are properly configured and ready to use.</p>
                    
                    <div class="config-details">
                        <h3>Configuration Details:</h3>
                        <ul>
                            <li><strong>Server:</strong> {server}</li>
                            <li><strong>Port:</strong> {port}</li>
                            <li><strong>Username:</strong> {username}</li>
                            <li><strong>From Email:</strong> {from_email}</li>
                        </ul>
                    </div>
                    
                    <p>You can now send emails through the RAKT DHARA system!</p>
                </div>
            </div>
        </body>
        </html>
        """.format(
            server=os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            port=os.getenv('SMTP_PORT', '587'),
            username=smtp_username,
            from_email=os.getenv('FROM_EMAIL', smtp_username)
        )
        
        result = send_email_via_smtp(
            recipient_email=test_email,
            subject=test_subject,
            message=test_message,
            html_message=test_html
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/send-message', methods=['POST'])
def send_message_to_donor():
    """Send a message to a donor via SMS, email, or WhatsApp"""
    data = request.get_json()
    
    donor_id = data.get('donor_id')
    message_type = data.get('message_type', 'sms')  # 'sms', 'email', 'whatsapp'
    message_content = data.get('message_content')
    request_id = data.get('request_id')
    
    if not donor_id or not message_content:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    # Get donor info
    donor = Donor.query.get(donor_id)
    if not donor:
        return jsonify({'success': False, 'error': 'Donor not found'})
    
    # Determine recipient based on message type
    if message_type == 'sms':
        recipient = donor.phone
    elif message_type == 'email':
        recipient = donor.email
    elif message_type == 'whatsapp':
        recipient = donor.phone
    else:
        return jsonify({'success': False, 'error': 'Invalid message type'})
    
    if not recipient:
        return jsonify({'success': False, 'error': f'Donor {message_type} not available'})
    
    # Send message based on type
    if message_type == 'sms':
        result = send_sms_via_twilio(recipient, message_content)
    elif message_type == 'email':
        subject = f"Blood Donation Request - {donor.name}"
        result = send_email_via_smtp(recipient, subject, message_content)
    elif message_type == 'whatsapp':
        result = send_whatsapp_via_api(recipient, message_content)
    
    # Save message record
    sent_message = SentMessage(
        donor_id=donor_id,
        request_id=request_id,
        message_type=message_type,
        recipient=recipient,
        message_content=message_content,
        status='sent' if result['success'] else 'failed'
    )
    
    try:
        db.session.add(sent_message)
        db.session.commit()
        
        return jsonify({
            'success': result['success'],
            'message_id': sent_message.id,
            'external_id': result.get('message_id'),
            'error': result.get('error')
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'})

@app.route('/api/messages/<int:message_id>/response', methods=['POST'])
def record_donor_response():
    """Record donor response to a sent message"""
    data = request.get_json()
    message_id = request.view_args['message_id']
    response = data.get('response')  # 'yes', 'no', 'maybe'
    
    if response not in ['yes', 'no', 'maybe']:
        return jsonify({'success': False, 'error': 'Invalid response'})
    
    try:
        sent_message = SentMessage.query.get(message_id)
        if not sent_message:
            return jsonify({'success': False, 'error': 'Message not found'})
        
        sent_message.response = response
        sent_message.response_received_at = datetime.utcnow()
        sent_message.status = 'responded'
        
        db.session.commit()
        
        # If donor responded YES, optionally auto-assign them
        if response == 'yes' and sent_message.request_id:
            # Auto-assign logic could go here
            pass
        
        return jsonify({'success': True, 'message': 'Response recorded'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/donors/<int:donor_id>/messages', methods=['GET'])
def get_donor_messages():
    """Get all messages sent to a donor"""
    donor_id = request.view_args['donor_id']
    
    messages = SentMessage.query.filter_by(donor_id=donor_id)\
                              .order_by(SentMessage.sent_at.desc())\
                              .limit(50).all()
    
    return jsonify([
        {
            'id': m.id,
            'message_type': m.message_type,
            'recipient': m.recipient,
            'message_content': m.message_content,
            'status': m.status,
            'response': m.response,
            'sent_at': m.sent_at.isoformat(),
            'response_received_at': m.response_received_at.isoformat() if m.response_received_at else None
        } for m in messages
    ])

# Automatic Donor Assignment System
@app.route('/api/requests/<int:request_id>/auto-assign', methods=['POST'])
def auto_assign_donor(request_id):
    """
    Automatically assign the best matching donor to a blood request
    """
    try:
        request_obj = BloodRequest.query.get_or_404(request_id)
        
        # Check if already assigned
        if request_obj.assigned_donor_id:
            return jsonify({
                'success': False,
                'message': f'Request already assigned to donor ID: {request_obj.assigned_donor_id}'
            }), 400
        
        # Get the best matching donor using intelligent matching
        best_match = get_best_donor_match(request_obj)
        
        if not best_match:
            return jsonify({
                'success': False,
                'message': 'No suitable donors found for this request'
            }), 404
        
        # Assign the donor
        request_obj.assigned_donor_id = best_match['donor']['id']
        request_obj.status = 'Assigned'
        request_obj.assignment_date = datetime.utcnow()
        request_obj.updated_at = datetime.utcnow()
        
        # Update donor availability
        donor = Donor.query.get(best_match['donor']['id'])
        donor.availability_status = 'Assigned'
        donor.is_available = False
        
        # Create notification for requester
        if request_obj.requester_id:
            notification = Notification(
                requester_id=request_obj.requester_id,
                request_id=request_obj.id,
                notification_type='donor_assigned',
                title='Donor Assigned',
                message=f'A donor has been assigned to your blood request for {request_obj.patient_name}. Donor: {donor.name}'
            )
            db.session.add(notification)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Request automatically assigned to {best_match["donor"]["name"]}',
            'assigned_donor': {
                'id': best_match['donor']['id'],
                'name': best_match['donor']['name'],
                'phone': best_match['donor']['phone'],
                'email': best_match['donor']['email'],
                'blood_type': best_match['donor']['blood_type'],
                'city': best_match['donor']['city']
            },
            'match_score': best_match['score'],
            'match_reasons': best_match['match_reasons']
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error auto-assigning donor: {str(e)}'
        }), 500

@app.route('/api/requests/bulk-auto-assign', methods=['POST'])
def bulk_auto_assign_donors():
    """
    Automatically assign donors to all pending blood requests
    """
    try:
        # Get all pending requests
        pending_requests = BloodRequest.query.filter_by(status='Pending').all()
        
        assignment_results = []
        successful_assignments = 0
        
        for request_obj in pending_requests:
            try:
                # Get the best matching donor
                best_match = get_best_donor_match(request_obj)
                
                if best_match:
                    # Assign the donor
                    request_obj.assigned_donor_id = best_match['donor']['id']
                    request_obj.status = 'Assigned'
                    request_obj.updated_at = datetime.utcnow()
                    
                    # Update donor availability
                    donor = Donor.query.get(best_match['donor']['id'])
                    donor.availability_status = 'Assigned'
                    donor.is_available = False
                    
                    successful_assignments += 1
                    
                    assignment_results.append({
                        'request_id': request_obj.id,
                        'patient_name': request_obj.patient_name,
                        'assigned_donor': best_match['donor']['name'],
                        'donor_id': best_match['donor']['id'],
                        'match_score': best_match['score'],
                        'status': 'success'
                    })
                else:
                    assignment_results.append({
                        'request_id': request_obj.id,
                        'patient_name': request_obj.patient_name,
                        'assigned_donor': None,
                        'donor_id': None,
                        'match_score': 0,
                        'status': 'no_match_found'
                    })
                    
            except Exception as e:
                assignment_results.append({
                    'request_id': request_obj.id,
                    'patient_name': request_obj.patient_name,
                    'assigned_donor': None,
                    'donor_id': None,
                    'match_score': 0,
                    'status': f'error: {str(e)}'
                })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Bulk assignment completed. {successful_assignments} requests assigned successfully.',
            'total_requests': len(pending_requests),
            'successful_assignments': successful_assignments,
            'assignment_results': assignment_results
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error in bulk assignment: {str(e)}'
        }), 500

def get_best_donor_match(request_obj):
    """
    Get the best matching donor for a blood request using intelligent matching
    """
    # Blood type compatibility mapping
    compatibility_map = {
        'A+': ['A+', 'A-', 'O+', 'O-'],
        'A-': ['A-', 'O-'],
        'B+': ['B+', 'B-', 'O+', 'O-'],
        'B-': ['B-', 'O-'],
        'AB+': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],  # Universal recipient
        'AB-': ['A-', 'B-', 'AB-', 'O-'],
        'O+': ['O+', 'O-'],
        'O-': ['O-']  # Universal donor
    }
    
    compatible_blood_types = compatibility_map.get(request_obj.blood_type, [])
    
    # Get compatible donors who are available
    compatible_donors = Donor.query.filter(
        Donor.blood_type.in_(compatible_blood_types),
        Donor.is_available == True,
        Donor.availability_status == 'Available'
    ).all()
    
    if not compatible_donors:
        return None
    
    # Calculate matching scores
    matched_donors = []
    for donor in compatible_donors:
        score = 0
        
        # Blood type compatibility score (exact match gets highest score)
        if donor.blood_type == request_obj.blood_type:
            score += 100  # Exact match
        elif donor.blood_type in compatible_blood_types:
            score += 80   # Compatible match
        
        # Location proximity score (same city gets bonus)
        if donor.city.lower() == request_obj.location.lower():
            score += 20
        
        # Availability score (recently available donors get bonus)
        if donor.last_donation_date:
            days_since_donation = (datetime.utcnow() - donor.last_donation_date).days
            if days_since_donation >= 56:  # 8 weeks minimum between donations
                score += 15
            elif days_since_donation >= 30:
                score += 10
        else:
            score += 15  # Never donated before
        
        # Experience score (experienced donors get slight bonus)
        if donor.donation_count > 0:
            score += min(donor.donation_count * 2, 10)  # Max 10 points for experience
        
        # Registration recency score (newer donors get slight bonus)
        days_since_registration = (datetime.utcnow() - donor.created_at).days
        if days_since_registration <= 30:
            score += 5
        
        # Urgency bonus (higher urgency gets priority)
        if request_obj.urgency == 'High':
            score += 10
        elif request_obj.urgency == 'Critical':
            score += 20
        
        matched_donors.append({
            'donor': {
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'phone': donor.phone,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'donation_count': donor.donation_count,
                'last_donation_date': donor.last_donation_date.isoformat() if donor.last_donation_date else None,
                'created_at': donor.created_at.isoformat()
            },
            'score': score,
            'match_reasons': get_match_reasons(donor, request_obj, score)
        })
    
    # Sort by score (highest first) and return the best match
    matched_donors.sort(key=lambda x: x['score'], reverse=True)
    
    return matched_donors[0] if matched_donors else None

@app.route('/api/requests/<int:request_id>/unassign', methods=['POST'])
def unassign_donor(request_id):
    """
    Unassign a donor from a blood request
    """
    try:
        request_obj = BloodRequest.query.get_or_404(request_id)
        
        if not request_obj.assigned_donor_id:
            return jsonify({
                'success': False,
                'message': 'No donor assigned to this request'
            }), 400
        
        # Get the assigned donor
        donor = Donor.query.get(request_obj.assigned_donor_id)
        
        # Update request status
        request_obj.assigned_donor_id = None
        request_obj.status = 'Pending'
        request_obj.updated_at = datetime.utcnow()
        
        # Update donor availability
        if donor:
            donor.availability_status = 'Available'
            donor.is_available = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Donor {donor.name if donor else "Unknown"} unassigned from request'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error unassigning donor: {str(e)}'
        }), 500

@app.route('/api/donors/<int:donor_id>/availability', methods=['PUT'])
def update_donor_availability(donor_id):
    data = request.get_json()
    donor = Donor.query.get_or_404(donor_id)
    
    if 'is_available' in data:
        donor.is_available = data['is_available']
    
    if 'availability_status' in data:
        donor.availability_status = data['availability_status']
        donor.is_available = data['availability_status'] == 'Available'
    
    if 'latitude' in data:
        donor.latitude = data['latitude']
    
    if 'longitude' in data:
        donor.longitude = data['longitude']
    
    if 'donation_count' in data:
        donor.donation_count = data['donation_count']
    
    if 'last_donation_date' in data:
        donor.last_donation_date = datetime.fromisoformat(data['last_donation_date'].replace('Z', '+00:00'))
        # Only increment donation_count if it wasn't explicitly set
        if 'donation_count' not in data:
            donor.donation_count += 1
    
    db.session.commit()
    return jsonify({'success': True, 'message': 'Donor availability updated successfully'})

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """
    Get comprehensive dashboard statistics including assignment information
    """
    try:
        # Basic counts
        total_donors = Donor.query.count()
        total_requests = BloodRequest.query.count()
        pending_requests = BloodRequest.query.filter_by(status='Pending').count()
        assigned_requests = BloodRequest.query.filter_by(status='Assigned').count()
        completed_requests = BloodRequest.query.filter_by(status='Completed').count()
        
        # Assignment statistics
        available_donors = Donor.query.filter_by(is_available=True, availability_status='Available').count()
        assigned_donors = Donor.query.filter_by(availability_status='Assigned').count()
        busy_donors = Donor.query.filter_by(availability_status='Busy').count()
        
        # Blood type distribution for available donors
        blood_type_distribution = {}
        available_donors_by_type = db.session.query(
            Donor.blood_type, 
            db.func.count(Donor.id)
        ).filter(
            Donor.is_available == True,
            Donor.availability_status == 'Available'
        ).group_by(Donor.blood_type).all()
        
        for blood_type, count in available_donors_by_type:
            blood_type_distribution[blood_type] = count
        
        # Recent assignments (last 7 days)
        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_assignments = BloodRequest.query.filter(
            BloodRequest.status == 'Assigned',
            BloodRequest.updated_at >= week_ago
        ).count()
        
        # Urgency distribution
        urgency_stats = {}
        urgency_counts = db.session.query(
            BloodRequest.urgency,
            db.func.count(BloodRequest.id)
        ).group_by(BloodRequest.urgency).all()
        
        for urgency, count in urgency_counts:
            urgency_stats[urgency] = count
        
        # Calculate lives saved based on total donations
        total_donations = sum(donor.donation_count for donor in Donor.query.all())
        lives_saved = total_donations * 3  # Each donation can save up to 3 lives
        
        return jsonify({
            'total_donors': total_donors,
            'total_requests': total_requests,
            'pending_requests': pending_requests,
            'assigned_requests': assigned_requests,
            'completed_requests': completed_requests,
            'available_donors': available_donors,
            'assigned_donors': assigned_donors,
            'busy_donors': busy_donors,
            'recent_assignments': recent_assignments,
            'blood_type_distribution': blood_type_distribution,
            'urgency_stats': urgency_stats,
            'assignment_rate': round((assigned_requests / total_requests * 100) if total_requests > 0 else 0, 2),
            'lives_saved': lives_saved
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching dashboard stats: {str(e)}'
        }), 500

@app.route('/api/admin/check')
def check_admin():
    admin = Admin.query.filter_by(email='admin@bloodbank.com').first()
    if admin:
        return jsonify({'exists': True, 'email': admin.email})
    else:
        # Create admin if it doesn't exist
        admin = Admin(email='admin@bloodbank.com', password='admin123')
        db.session.add(admin)
        db.session.commit()
        return jsonify({'exists': False, 'created': True, 'email': 'admin@bloodbank.com'})


@app.route('/api/user/logout', methods=['POST'])
def user_logout():
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    return jsonify({'success': True, 'message': 'Admin logged out successfully'})

@app.route('/api/donors/<int:donor_id>', methods=['DELETE'])
def delete_donor(donor_id):
    donor = Donor.query.get_or_404(donor_id)
    db.session.delete(donor)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Donor deleted successfully'})

@app.route('/api/requesters/<int:requester_id>', methods=['DELETE'])
def delete_requester(requester_id):
    requester = Requester.query.get_or_404(requester_id)
    db.session.delete(requester)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Requester deleted successfully'})

@app.route('/api/blood-inventory', methods=['GET'])
def get_blood_inventory():
    # Get all donors grouped by blood type
    donors_by_type = {}
    all_donors = Donor.query.all()
    
    for donor in all_donors:
        blood_type = donor.blood_type
        if blood_type not in donors_by_type:
            donors_by_type[blood_type] = []
        donors_by_type[blood_type].append({
            'id': donor.id,
            'name': donor.name,
            'email': donor.email,
            'phone': donor.phone,
            'city': donor.city,
            'availability_status': donor.availability_status,
            'is_available': donor.is_available,
            'donation_count': donor.donation_count,
            'created_at': donor.created_at.isoformat()
        })
    
    # Convert to list sorted by blood type
    inventory = []
    for blood_type in sorted(donors_by_type.keys()):
        inventory.append({
            'blood_type': blood_type,
            'total_donors': len(donors_by_type[blood_type]),
            'donors': donors_by_type[blood_type]
        })
    
    return jsonify(inventory)

@app.route('/api/smart-match', methods=['POST'])
def smart_donor_matching():
    data = request.get_json()
    required_blood_type = data.get('blood_type')
    request_location = data.get('location', {})
    max_distance = data.get('max_distance', 50)  # Default 50 miles
    availability_filter = data.get('availability_filter', 'Available')
    
    # Blood type compatibility mapping
    blood_compatibility = {
        'A+': ['A+', 'A-', 'O+', 'O-'],
        'A-': ['A-', 'O-'],
        'B+': ['B+', 'B-', 'O+', 'O-'],
        'B-': ['B-', 'O-'],
        'AB+': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],  # Universal recipient
        'AB-': ['A-', 'B-', 'AB-', 'O-'],
        'O+': ['O+', 'O-'],
        'O-': ['O-']  # Universal donor
    }
    
    compatible_blood_types = blood_compatibility.get(required_blood_type, [required_blood_type])
    
    # Get compatible donors
    compatible_donors = Donor.query.filter(
        Donor.blood_type.in_(compatible_blood_types),
        Donor.is_available == True,
        Donor.availability_status == availability_filter
    ).all()
    
    # Calculate distance and filter
    matched_donors = []
    for donor in compatible_donors:
        # Calculate distance (simplified - in real app, use proper geocoding)
        distance = calculate_distance(request_location, donor.city)
        
        if distance <= max_distance:
            matched_donors.append({
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'phone': donor.phone,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'availability_status': donor.availability_status,
                'distance_miles': round(distance, 1),
                'last_donation': donor.last_donation_date.isoformat() if donor.last_donation_date else None,
                'donation_count': donor.donation_count,
                'compatibility_score': calculate_compatibility_score(donor, required_blood_type, distance)
            })
    
    # Sort by distance first (nearest first), then by compatibility score (highest first)
    matched_donors.sort(key=lambda x: (x['distance_miles'], -x['compatibility_score']))
    
    return jsonify({
        'required_blood_type': required_blood_type,
        'total_matches': len(matched_donors),
        'matches': matched_donors[:5],  # Return top 5 matches initially
        'has_more': len(matched_donors) > 5,  # Indicate if there are more results
        'remaining_count': max(0, len(matched_donors) - 5),  # Count of remaining results
        'filters_applied': {
            'max_distance': max_distance,
            'availability': availability_filter,
            'compatible_blood_types': compatible_blood_types
        }
    })

def calculate_distance(request_location, donor_city):
    # Simplified distance calculation
    # In a real app, you would use geocoding APIs to get coordinates
    # and calculate actual distances using Haversine formula
    
    # Mock distance calculation based on city names
    city_distances = {
        'Test City': {
            'Test City': 0, 'New York': 8, 'Kolkata': 12, 'Mumbai': 15, 
            'Delhi': 10, 'Bangalore': 18, 'Chennai': 20, 'Hyderabad': 16,
            'Pune': 14, 'Ahmedabad': 22, 'Jaipur': 25, 'Lucknow': 28
        },
        'New York': {
            'Test City': 8, 'New York': 0, 'Kolkata': 5, 'Mumbai': 12,
            'Delhi': 8, 'Bangalore': 15, 'Chennai': 18, 'Hyderabad': 14
        },
        'Kolkata': {
            'Test City': 12, 'New York': 5, 'Kolkata': 0, 'Mumbai': 8,
            'Delhi': 6, 'Bangalore': 12, 'Chennai': 10, 'Hyderabad': 9
        }
    }
    
    request_city = request_location.get('city', 'Test City')
    
    # Check if we have specific distance data
    if request_city in city_distances and donor_city in city_distances[request_city]:
        return city_distances[request_city][donor_city]
    
    # Default distance calculation - more realistic
    if request_city.lower() == donor_city.lower():
        return 0
    else:
        # Return a random but reasonable distance between 3-20 miles
        import random
        return random.randint(3, 20)

def calculate_compatibility_score(donor, required_blood_type, distance):
    score = 100  # Base score
    
    # Blood type compatibility bonus
    if donor.blood_type == required_blood_type:
        score += 50  # Perfect match
    elif donor.blood_type == 'O-':
        score += 30  # Universal donor bonus
    elif required_blood_type == 'AB+':
        score += 20  # Universal recipient
    
    # Distance penalty
    if distance <= 5:
        score += 20  # Very close
    elif distance <= 15:
        score += 10  # Close
    elif distance <= 30:
        score += 5   # Moderate
    else:
        score -= 10  # Far
    
    # Availability bonus
    if donor.availability_status == 'Available':
        score += 15
    elif donor.availability_status == 'Busy':
        score += 5
    
    # Donation history bonus
    if donor.donation_count > 5:
        score += 10  # Experienced donor
    elif donor.donation_count > 0:
        score += 5   # Has donated before
    
    # Recent donation penalty (can't donate too frequently)
    if donor.last_donation_date:
        days_since_donation = (datetime.utcnow() - donor.last_donation_date).days
        if days_since_donation < 56:  # Less than 8 weeks
            score -= 30  # Can't donate yet
    
    return score  # Return the calculated score

@app.route('/api/donors/<int:donor_id>/donation', methods=['POST'])
def record_donation(donor_id):
    donor = Donor.query.get_or_404(donor_id)
    
    # Update donation record
    donor.last_donation_date = datetime.utcnow()
    donor.donation_count += 1
    donor.availability_status = 'Busy'  # Temporarily unavailable after donation
    donor.is_available = False
    
    db.session.commit()
    return jsonify({'success': True, 'message': 'Donation recorded successfully'})

@app.route('/api/donation/complete', methods=['POST'])
def complete_donation():
    """
    Mark a donation as completed and generate certificate
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['donor_id', 'units_donated', 'blood_type', 'donation_location']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        donor_id = data['donor_id']
        donor = Donor.query.get_or_404(donor_id)
        
        # Create donation completion record
        completion = DonationCompletion(
            donor_id=donor_id,
            request_id=data.get('request_id'),
            units_donated=data['units_donated'],
            blood_type=data['blood_type'],
            donation_location=data['donation_location'],
            medical_officer=data.get('medical_officer', 'Dr. Medical Officer'),
            notes=data.get('notes', ''),
            donation_date=datetime.utcnow()
        )
        
        # Generate certificate ID
        certificate_id = f"CERT-{donor_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        completion.certificate_id = certificate_id
        completion.certificate_generated = True
        
        db.session.add(completion)
        
        # Update donor's donation count and availability
        donor.donation_count += 1
        donor.last_donation_date = datetime.utcnow()
        donor.availability_status = 'Busy'  # Temporarily unavailable
        donor.is_available = False
        
        # Update blood request status if linked
        if data.get('request_id'):
            blood_request = BloodRequest.query.get(data['request_id'])
            if blood_request:
                blood_request.status = 'Delivered'
                blood_request.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Donation completed successfully',
            'certificate_id': certificate_id,
            'donation_id': completion.id,
            'donor_name': donor.name,
            'donation_date': completion.donation_date.isoformat(),
            'units_donated': completion.units_donated,
            'blood_type': completion.blood_type
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error completing donation: {str(e)}'}), 500

@app.route('/api/donation/certificate/<certificate_id>', methods=['GET'])
def get_donation_certificate(certificate_id):
    """
    Get donation certificate details
    """
    try:
        completion = DonationCompletion.query.filter_by(certificate_id=certificate_id).first()
        
        if not completion:
            return jsonify({'success': False, 'message': 'Certificate not found'}), 404
        
        return jsonify({
            'success': True,
            'certificate': {
                'certificate_id': completion.certificate_id,
                'donor_name': completion.donor.name,
                'donor_email': completion.donor.email,
                'donor_phone': completion.donor.phone,
                'donation_date': completion.donation_date.isoformat(),
                'units_donated': completion.units_donated,
                'blood_type': completion.blood_type,
                'donation_location': completion.donation_location,
                'medical_officer': completion.medical_officer,
                'notes': completion.notes,
                'created_at': completion.created_at.isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error retrieving certificate: {str(e)}'}), 500

@app.route('/api/donor/<int:donor_id>/donation-history', methods=['GET'])
def get_donor_donation_history(donor_id):
    """
    Get complete donation history for a donor
    """
    try:
        donor = Donor.query.get_or_404(donor_id)
        completions = DonationCompletion.query.filter_by(donor_id=donor_id).order_by(DonationCompletion.donation_date.desc()).all()
        
        history = []
        for completion in completions:
            history.append({
                'donation_id': completion.id,
                'certificate_id': completion.certificate_id,
                'donation_date': completion.donation_date.isoformat(),
                'units_donated': completion.units_donated,
                'blood_type': completion.blood_type,
                'donation_location': completion.donation_location,
                'medical_officer': completion.medical_officer,
                'certificate_generated': completion.certificate_generated,
                'notes': completion.notes
            })
        
        return jsonify({
            'success': True,
            'donor': {
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'total_donations': donor.donation_count,
                'last_donation_date': donor.last_donation_date.isoformat() if donor.last_donation_date else None
            },
            'donation_history': history,
            'total_completions': len(history)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error retrieving donation history: {str(e)}'}), 500

@app.route('/api/donations/completed', methods=['GET'])
def get_all_completed_donations():
    """
    Get all completed donations for admin view
    """
    try:
        completions = DonationCompletion.query.order_by(DonationCompletion.donation_date.desc()).all()
        
        donations = []
        for completion in completions:
            donations.append({
                'donation_id': completion.id,
                'certificate_id': completion.certificate_id,
                'donor_name': completion.donor.name,
                'donor_email': completion.donor.email,
                'donation_date': completion.donation_date.isoformat(),
                'units_donated': completion.units_donated,
                'blood_type': completion.blood_type,
                'donation_location': completion.donation_location,
                'medical_officer': completion.medical_officer,
                'certificate_generated': completion.certificate_generated,
                'notes': completion.notes
            })
        
        return jsonify({
            'success': True,
            'completed_donations': donations,
            'total_donations': len(donations)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error retrieving completed donations: {str(e)}'}), 500

@app.route('/api/donor/<int:donor_id>/info', methods=['GET'])
def get_donor_info(donor_id):
    """
    Get donor information for certificate generation
    """
    try:
        donor = Donor.query.get(donor_id)
        
        if not donor:
            return jsonify({'success': False, 'message': 'Donor not found'}), 404
        
        return jsonify({
            'success': True,
            'donor': {
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'phone': donor.phone,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'certificate_id': donor.certificate_id,
                'donation_count': donor.donation_count,
                'last_donation_date': donor.last_donation_date.isoformat() if donor.last_donation_date else None,
                'is_available': donor.is_available,
                'availability_status': donor.availability_status
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error retrieving donor info: {str(e)}'}), 500

@app.route('/api/certificate/generate/<certificate_id>', methods=['GET'])
def generate_professional_certificate(certificate_id):
    """
    Generate professional certificate in the exact format requested
    """
    try:
        completion = DonationCompletion.query.filter_by(certificate_id=certificate_id).first()
        
        if not completion:
            return jsonify({'success': False, 'message': 'Certificate not found'}), 404
        
        # Get donor's total donation count
        total_donations = completion.donor.donation_count
        
        # Generate certificate data with comprehensive donor information
        certificate_data = {
            'certificate_id': completion.certificate_id,
            'donor_name': completion.donor.name,
            'donation_count': total_donations,
            'donation_count_text': get_donation_count_text(total_donations),
            'donation_date': completion.donation_date.strftime('%B %d, %Y'),
            'blood_type': completion.blood_type,
            'donation_location': completion.donation_location,
            'medical_officer': completion.medical_officer,
            'units_donated': completion.units_donated,
            # Additional donor details
            'donor_email': completion.donor.email,
            'donor_phone': completion.donor.phone,
            'donor_city': completion.donor.city,
            'registration_date': completion.donor.created_at.strftime('%B %d, %Y'),
            'last_donation_date': completion.donor.last_donation_date.strftime('%B %d, %Y') if completion.donor.last_donation_date else 'First Donation',
            'donor_id': completion.donor.id,
            'certificate_generated_date': datetime.utcnow().strftime('%B %d, %Y'),
            'certificate_generated_time': datetime.utcnow().strftime('%I:%M %p')
        }
        
        return jsonify({
            'success': True,
            'certificate': certificate_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error generating certificate: {str(e)}'}), 500

def get_donation_count_text(count):
    """
    Convert donation count to ordinal text (e.g., 1 -> "FIRST", 2 -> "SECOND", etc.)
    """
    ordinals = {
        1: "FIRST", 2: "SECOND", 3: "THIRD", 4: "FOURTH", 5: "FIFTH",
        6: "SIXTH", 7: "SEVENTH", 8: "EIGHTH", 9: "NINTH", 10: "TENTH",
        11: "ELEVENTH", 12: "TWELFTH", 13: "THIRTEENTH", 14: "FOURTEENTH", 15: "FIFTEENTH",
        16: "SIXTEENTH", 17: "SEVENTEENTH", 18: "EIGHTEENTH", 19: "NINETEENTH", 20: "TWENTIETH"
    }
    
    if count in ordinals:
        return f"THE {ordinals[count]} BLOOD DONATION"
    else:
        return f"THE {count}TH BLOOD DONATION"

def generate_donor_certificate_id(donor_id, donor_name):
    """
    Generate a unique certificate ID for a donor
    Format: DONOR-{donor_id}-{initials}-{timestamp}
    """
    # Get initials from donor name
    initials = ''.join([word[0].upper() for word in donor_name.split() if word])
    if len(initials) > 3:
        initials = initials[:3]
    
    # Generate timestamp
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    
    # Create certificate ID
    certificate_id = f"DONOR-{donor_id}-{initials}-{timestamp}"
    
    return certificate_id

@app.route('/api/donors/generate-certificates', methods=['POST'])
def generate_certificates_for_existing_donors():
    """
    Generate certificate IDs for existing donors who don't have them
    """
    try:
        donors_without_certificates = Donor.query.filter_by(certificate_id=None).all()
        
        updated_count = 0
        for donor in donors_without_certificates:
            certificate_id = generate_donor_certificate_id(donor.id, donor.name)
            donor.certificate_id = certificate_id
            updated_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Generated certificate IDs for {updated_count} donors',
            'updated_count': updated_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error generating certificates: {str(e)}'}), 500

@app.route('/api/user/<email>')
def get_user_by_email(email):
    # Try to find donor first
    donor = Donor.query.filter_by(email=email).first()
    if donor:
        return jsonify({
            'user_type': 'donor',
            'user': {
                'id': donor.id,
                'name': donor.name,
                'email': donor.email,
                'phone': donor.phone,
                'blood_type': donor.blood_type,
                'city': donor.city,
                'availability_status': donor.availability_status,
                'donation_count': donor.donation_count,
                'created_at': donor.created_at.isoformat()
            }
        })
    
    # Try to find requester
    requester = Requester.query.filter_by(email=email).first()
    if requester:
        return jsonify({
            'user_type': 'requester',
            'user': {
                'id': requester.id,
                'name': requester.name,
                'email': requester.email,
                'phone': requester.phone,
                'city': requester.city,
                'created_at': requester.created_at.isoformat()
            }
        })
    
    return jsonify({'error': 'User not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
