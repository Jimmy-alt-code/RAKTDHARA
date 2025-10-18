#!/usr/bin/env python3
"""
Script to create test users for the Blood Bank system
"""

from mvp_app import app, db, Donor
from datetime import datetime

def create_test_users():
    with app.app_context():
        # Create test users if they don't exist
        test_users = [
            {
                'name': 'Jimmy Carter',
                'email': 'jimmy@bloodbank.com',
                'password': 'jimmy123',
                'phone': '9876543215',
                'blood_type': 'O-',
                'city': 'New York',
                'certificate_id': 'DONOR-9-J-20251011162123',
                'donation_count': 20,
                'is_available': True
            },
            {
                'name': 'Ayushman Kumar',
                'email': 'ayushman@bloodbank.com',
                'password': 'ayushman123',
                'phone': '9876543212',
                'blood_type': 'O+',
                'city': 'Bangalore',
                'certificate_id': 'DONOR-6-A-20251011162123',
                'donation_count': 15,
                'is_available': True
            },
            {
                'name': 'Rahul Gandhi',
                'email': 'rahul@bloodbank.com',
                'password': 'rahul123',
                'phone': '9876543213',
                'blood_type': 'A+',
                'city': 'Delhi',
                'certificate_id': 'DONOR-7-R-20251011162123',
                'donation_count': 12,
                'is_available': True
            },
            {
                'name': 'Priya Sharma',
                'email': 'priya@bloodbank.com',
                'password': 'priya123',
                'phone': '9876543214',
                'blood_type': 'B+',
                'city': 'Mumbai',
                'certificate_id': 'DONOR-8-P-20251011162123',
                'donation_count': 8,
                'is_available': False
            }
        ]
        
        for user_data in test_users:
            # Check if user already exists
            existing_user = Donor.query.filter_by(email=user_data['email']).first()
            if not existing_user:
                user = Donor(
                    name=user_data['name'],
                    email=user_data['email'],
                    password=user_data['password'],
                    phone=user_data['phone'],
                    blood_type=user_data['blood_type'],
                    city=user_data['city'],
                    certificate_id=user_data['certificate_id'],
                    donation_count=user_data['donation_count'],
                    is_available=user_data['is_available'],
                    created_at=datetime.utcnow()
                )
                db.session.add(user)
                print(f"Created user: {user_data['name']} ({user_data['email']})")
            else:
                print(f"User already exists: {user_data['name']} ({user_data['email']})")
        
        db.session.commit()
        print("Test users created successfully!")

if __name__ == '__main__':
    create_test_users()
