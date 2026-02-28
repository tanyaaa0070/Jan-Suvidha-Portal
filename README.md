# Jan Suvidha Portal  
AI-Assisted Welfare Scheme Awareness & Underutilization Monitoring System

---

## Problem Statement

Government welfare schemes in India—covering areas such as digital literacy, housing, education, health, and direct benefit transfers—remain significantly underutilized despite being available online.

The major reasons include:
- Complex legal and administrative language  
- Lack of awareness about available schemes  
- Confusion regarding eligibility criteria  
- Unclear documentation requirements  
- Digital illiteracy and language barriers  
- Absence of reminders or follow-up mechanisms  

As a result, many eligible citizens fail to apply, while allocated government funds remain unused.

---

## Solution Overview

**Jan Suvidha Portal** is a legal-safe academic prototype designed to address these issues using a **hybrid approach of AI-assisted interaction and rule-based decision logic**.

The system:
- Helps citizens discover schemes they are eligible for  
- Simplifies scheme information using local languages  
- Provides voice assistance for accessibility  
- Sends reminders to eligible but non-applied users  
- Enables administrators to identify underutilized regions through analytics  

> **Note:**  
> This project uses **dummy scheme data only**.  
> No real government data, scraping, or official verification is performed.

---

## Target Users

### Citizen Portal
- Rural citizens  
- BPL (Below Poverty Line) families  
- Farmers  
- Women, elderly, and persons with disabilities  
- SC/ST/OBC communities  
- Digitally illiterate or semi-literate users  

### Admin Portal
- Single **Government Welfare Admin** (demo role)
- Full visibility across:
  - State
  - District
  - Village (using filters, not role separation)

---

## Key Features

### Citizen Portal
- Multilingual support (English, Hindi, Kannada)
- AI-assisted dynamic questioning (Yes/No and one-word answers)
- Voice assistance using Text-to-Speech
- Scheme eligibility discovery
- Document checklist and verification
- Benefit probability estimation
- SMS reminders for eligible but non-applied users
- Out-of-context and invalid answer detection

### Admin Portal
- Single admin login
- Eligible vs Applied analytics
- State / District / Village-wise filtering
- Underutilization detection
- Automated reminder triggering
- Scheme-wise utilization overview

---

## AI Usage (Strictly Limited)

### AI is used for:
- Simplifying questions into local languages
- Conversational flow for dynamic questioning

### AI is NOT used for:
- Eligibility decision making
- Sending reminders
- Admin analytics
- Final approval logic

All eligibility checks, reminders, and analytics are **rule-based** to ensure transparency and reliability.

---

## APIs and Tools Used

| # | API / Tool | Purpose |
|---|-----------|--------|
| 1 | MongoDB | Central database for users, schemes, applications |
| 2 | Google Gemini AI | Simplifying questions and language |
| 3 | Fast2SMS | Sending SMS reminders |
| 4 | Google Translate TTS | Voice output in local languages |
| 5 | Web Speech API | Browser-based voice input and output |
| 6 | Google Fonts | Regional language font support |
| 7 | Font Awesome | UI icons |

---

## Tech Stack

### Frontend
- HTML  
- CSS  
- JavaScript  
- Web Speech API  

### Backend
- **Django** – authentication, admin portal, analytics, reminders  
- **Flask** – AI microservice (Gemini interaction and document logic)

### Database
- **MongoDB** (dummy data only)

---

## Project Structure
<img width="904" height="650" alt="image" src="https://github.com/user-attachments/assets/1b441249-cee8-47a7-bef5-0abf59c38f98" />


---

## Reminder Logic (Rule-Based)

If:
- A user is **eligible** for a scheme  
- AND the user has **not applied**

Then:
- An SMS reminder is sent using **Fast2SMS**

Example message:
> “You are eligible for government welfare schemes but have not applied yet. Please apply soon.”

No AI is involved in reminder decision-making.

---

## Privacy and Ethics

- Dummy data only  
- No Aadhaar or official verification  
- Explicit user consent for notifications  
- No scraping of government websites  
- Academic and hackathon compliant design  

---

## Demo Scenario

- One village with 100 eligible users  
- Only 50 users have applied  
- Remaining 50 are flagged as non-applied  
- SMS reminders are triggered  
- Admin dashboard highlights underutilization  

---

## Why This Project Stands Out

- Addresses a real governance problem  
- Responsible and controlled AI usage  
- Inclusive design with voice and multilingual support  
- Clear admin-level analytics  
- High social impact  
- Suitable for hackathons and academic evaluation  

---

## One-Line Summary

> **Jan Suvidha Portal uses AI to guide citizens, rule-based logic to ensure trust, and analytics to reduce welfare scheme underutilization.**

---

## Disclaimer

This project is an **academic / hackathon prototype**.  
All schemes, users, and data are **dummy and simulated** for demonstration purposes only.
