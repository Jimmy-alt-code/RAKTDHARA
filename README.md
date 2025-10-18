# 🩸 MVP Blood Bank Platform - RAKT DHARA

A simplified, all-in-one blood bank management system with essential features for donor registration, blood requests, and admin management.

## 🎯 **Two User Types System**

### **🩸 Blood Donors**
- **Registration:** Name, Email, Phone, Blood Type, City, Password
- **Features:** Can donate blood, view their profile, update information
- **Login:** Uses donor credentials to access donor dashboard
- **Purpose:** Provide blood donations to help patients in need

### **🏥 Blood Requesters**
- **Registration:** Name, Email, Phone, City, Password
- **Features:** Can request blood, view request status, manage requests
- **Login:** Uses requester credentials to access requester dashboard
- **Purpose:** Request blood for patients who need transfusions

### **👨‍💼 Admin**
- **Access:** Full system control and management
- **Features:** Manage donors, requesters, requests, blood inventory
- **Login:** Admin credentials for complete system oversight
- **Purpose:** Oversee the entire blood bank operation

### **Overview Tab**
- **Statistics Dashboard** - Total donors, requests, pending/completed counts
- **Recent Donors** - Latest registered donors
- **Recent Requests** - Latest blood requests

### **Request Management Tab**
- **Accept/Reject Requests** - Approve or deny blood requests
- **Mark as Delivered** - Update request status when blood is delivered
- **Cancel Requests** - Cancel requests if needed
- **View All Details** - Patient info, blood type, units, location, contact

### **User Management Tab**
- **View All Donors** - Complete donor information
- **Delete Users** - Remove donors from the system
- **Donor Details** - Name, email, phone, blood type, city, registration date

### **Blood Inventory Tab**
- **Blood Type Dashboard** - Organized by blood type (A+, A-, B+, B-, AB+, AB-, O+, O-)
- **Donor Count** - Total donors available for each blood type
- **Donor Details** - Contact information and registration dates
- **Visual Cards** - Easy-to-read format for each blood type

## 🎯 Features

### **👤 User Management**
- Donor Registration
- Admin Authentication
- User Session Management

### **🩸 Blood Request System**
- Create Blood Requests
- View Request Status
- Update Request Status (Accept/Reject)
- Request History

### **📊 Dashboard & Analytics**
- Total Donors Count
- Total Requests Count
- Pending Requests Count
- Real-time Statistics

### **👥 Donor Management**
- Register New Donors
- View All Donors
- Donor Information Display
- Blood Type Tracking

### **🏥 Request Management**
- Create Blood Requests
- View All Requests
- Accept/Reject Requests
- Status Updates

### **🔐 Security Features**
- Admin Login System
- Session Management
- Form Validation
- Data Protection

### **📱 User Interface**
- Responsive Design
- Mobile-Friendly
- Clean UI/UX
- Real-time Updates

### **⚙️ System Features**
- Database Management
- API Endpoints
- Error Handling
- Auto-initialization

## 🚀 Quick Start

1. **Install Dependencies:**
   ```bash
   pip install -r mvp_requirements.txt
   ```

2. **Run the Application:**
   ```bash
   python mvp_app.py
   ```

3. **Access the Application:**
   - Main Interface: http://127.0.0.1:5000
   - Admin Dashboard: http://127.0.0.1:5000/admin

## 🔑 Simple Login System

### One-Click Login with Direct Redirect
- **URL:** http://127.0.0.1:5000
- **Just enter email and password** - system automatically detects if you're a donor or admin
- **Direct redirect** to dashboard - no intermediate screens!
- **No need to select user type** - it's automatic!

### Login Credentials

#### Admin Login
- **Email:** admin@bloodbank.com
- **Password:** admin123
- **Redirects to:** Admin Dashboard

#### Donor Login
- **Step 1:** Register as a donor (fill out the form with your password)
- **Step 2:** Login using your email and password
- **Redirects to:** Donor Dashboard

#### Requester Login
- **Step 1:** Register as a requester (fill out the form with your password)
- **Step 2:** Login using your email and password
- **Redirects to:** Requester Dashboard

#### Test Users (Already Created)
- **Donor:** test@example.com / test123
- **Requester:** requester@example.com / req123

## 📁 Project Structure
```
├── mvp_app.py              # Main application file
├── mvp_index.html          # Main user interface
├── mvp_admin.html          # Admin dashboard
├── mvp_requirements.txt    # Python dependencies
├── instance/
│   └── mvp_blood_bank.db   # SQLite database
└── README.md              # This file
```

## 🛠️ Technology Stack
- **Backend:** Flask (Python)
- **Database:** SQLite
- **Frontend:** HTML, CSS, JavaScript
- **Styling:** Custom CSS with responsive design

## 📋 API Endpoints

### Admin
- `POST /api/admin/login` - Admin login
- `GET /api/admin/me` - Get admin info

### Donors
- `GET /api/donors` - Get all donors
- `POST /api/donors` - Register new donor

### Blood Requests
- `GET /api/requests` - Get all requests
- `POST /api/requests` - Create new request
- `PUT /api/requests/<id>` - Update request status

### Dashboard
- `GET /api/dashboard/stats` - Get dashboard statistics

## 🎨 UI Features
- **Responsive Design:** Works on desktop, tablet, and mobile
- **Modern Interface:** Clean, professional design
- **Real-time Updates:** Live statistics and data
- **User-Friendly:** Intuitive navigation and forms

## 🔧 Development
The application is built as a single-file Flask application for simplicity and easy deployment. All models, routes, and functionality are contained in `mvp_app.py`.

## 📝 Notes
- Database is automatically created on first run
- Default admin account is created automatically
- All data is stored in SQLite database
- Application runs on port 5000 by default
