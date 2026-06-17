Now let me get the file listing:Now let me get a sample of key Python files to understand the project better:Based on my analysis of all the files in your repository, here's a comprehensive README summary:


**Project Overview**
This is a **Quantum Key Distribution (QKD) Security System** with eavesdropping detection, machine learning-based threat analysis, and explainable AI (XAI) capabilities. It implements secure message passing between clients with quantum-inspired key distribution protocols.

**Key Components**

**1. Servers** (`/servers`)
- **qkd_server.py**: Core server with Flask + WebSocket for secure communication, CSV-based dataset loading, and 6-digit QKD code generation
- **qkd_dataset_server.py**: Serves datasets for training and testing
- **qkd_server_email.py**: Extended version with email alert capabilities
- **qkd_server1.py**: Enhanced server with additional security features

**2. Clients** (`/clients`)
- **device_client.py**: Base client for secure messaging with QKD authentication challenges
- **device_client_gui.py**: GUI-based client interface with enhanced user experience
- **device_client_alert.py**: Client with alert/notification system for eavesdropping detection
- **eavesdropper_client.py**: Simulation client to test eavesdropping detection mechanisms

**3. ML Models** (`/models`)
- **train_model.py**: Random Forest model trainer for eavesdropping detection
- **qkd_xai.py**: SHAP-based explainability engine that provides human-readable insights into threat predictions
- **explain_qkd_model.py**: Generates feature importance and threat explanations
- **inspect_model.py**: Model inspection and validation utilities

**4. Utilities** (`/utils`)
- **crypto_utils.py**: Cryptographic functions (OTP encryption, bit conversion)
- **qkd_sim.py**: QKD protocol simulation logic
- **leakage_check.py**: Detects information leakage and statistical anomalies
- **key_manager.py**: Manages cryptographic key generation and storage
- **email_sender.py**: Sends alert notifications via email

**5. Dataset Management** (`/dataset`)
- **data_loader.py**: Loads and preprocesses quantum channel data
- **logs_parser.py**: Parses server logs into structured format
- **visualize_data.py**: Data visualization and statistical analysis
- **test_loader.py**: Test data loading utilities

**Core Features**
✅ **Secure Message Encryption** - OTP-based encryption with quantum channel metrics  
✅ **Eavesdropping Detection** - ML-based anomaly detection  
✅ **Explainable AI** - SHAP-based feature importance visualization  
✅ **Real-time Dashboard** - Live monitoring of secure channels  
✅ **QKD Authentication** - 6-digit code verification system  
✅ **CSV Logging** - Persistent event tracking and audit trail

**Dependencies**
- Flask, Flask-SocketIO for networking
- NumPy, Pandas, Scikit-learn for ML
- SHAP for model explainability
- Eventlet for async operations
  
**Quick Start**
```bash
pip install -r requirements.txt
bash run.sh  # Trains model, generates explanations, starts Streamlit dashboard
```
