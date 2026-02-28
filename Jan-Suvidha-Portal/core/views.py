"""
Views for Jan Suvidha Portal — Citizen & Admin.
"""
import json
import uuid
import requests
from datetime import datetime, timezone
from bson import ObjectId
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from .db import get_collection
from .rule_engine import find_eligible_schemes, calculate_benefit_probability, calculate_document_completeness
from .dummy_data import DUMMY_SCHEMES, LOCATIONS


# ─── Citizen Page Views ───

def landing(request):
    return render(request, 'landing.html')


def register(request):
    lang = request.GET.get('lang', 'en')
    return render(request, 'citizen/register.html', {'lang': lang})


def questionnaire(request):
    user_id = request.session.get('user_id')
    lang = request.session.get('language', 'en')
    if not user_id:
        return redirect('register')
    return render(request, 'citizen/questionnaire.html', {
        'user_id': user_id, 'lang': lang
    })


def results(request):
    user_id = request.session.get('user_id')
    lang = request.session.get('language', 'en')
    if not user_id:
        return redirect('register')
    schemes = request.session.get('eligible_schemes', [])
    return render(request, 'citizen/results.html', {
        'user_id': user_id, 'lang': lang,
        'schemes_json': json.dumps(schemes),
    })


def documents(request, scheme_id):
    user_id = request.session.get('user_id')
    lang = request.session.get('language', 'en')
    if not user_id:
        return redirect('register')
    scheme = None
    for s in DUMMY_SCHEMES:
        if s['scheme_id'] == scheme_id:
            scheme = s
            break
    return render(request, 'citizen/documents.html', {
        'user_id': user_id, 'lang': lang,
        'scheme': json.dumps(scheme) if scheme else '{}',
        'scheme_id': scheme_id,
    })


# ─── Citizen API Endpoints ───

@csrf_exempt
@require_POST
def api_switch_language(request):
    """Quick endpoint to switch user's session language."""
    try:
        data = json.loads(request.body)
        language = data.get('language', 'en')
        if language in ('en', 'hi', 'kn', 'te', 'ta'):
            request.session['language'] = language
            return JsonResponse({'success': True, 'language': language})
        return JsonResponse({'error': 'Invalid language'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_POST
def api_register(request):
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
        name = data.get('name', '').strip()
        language = data.get('language', 'en')
        whatsapp = data.get('whatsapp_consent', False)

        if not phone or len(phone) < 10:
            return JsonResponse({'error': 'Valid phone number required'}, status=400)

        users = get_collection('users')
        existing = users.find_one({'phone': phone})
        if existing:
            user_id = str(existing['_id'])
        else:
            result = users.insert_one({
                'phone': phone, 'name': name, 'language': language,
                'whatsapp_consent': whatsapp,
                'village': '', 'district': '', 'state': '',
                'created_at': datetime.now(timezone.utc),
            })
            user_id = str(result.inserted_id)

        request.session['user_id'] = user_id
        request.session['language'] = language
        return JsonResponse({'success': True, 'user_id': user_id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def api_check_eligibility(request):
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id') or request.session.get('user_id')
        responses = data.get('responses', {})
        language = data.get('language', request.session.get('language', 'en'))

        if not responses:
            return JsonResponse({'error': 'No responses provided'}, status=400)

        # Find eligible schemes using rule engine
        eligible = find_eligible_schemes(responses, DUMMY_SCHEMES)

        # Store user responses
        resp_col = get_collection('user_responses')
        matched_ids = [r['scheme']['scheme_id'] for r in eligible]
        resp_col.insert_one({
            'user_id': user_id,
            'session_id': str(uuid.uuid4()),
            'responses': responses,
            'matched_schemes': matched_ids,
            'created_at': datetime.now(timezone.utc),
        })

        # Create application entries
        apps_col = get_collection('applications')
        for r in eligible:
            sid = r['scheme']['scheme_id']
            existing = apps_col.find_one({'user_id': user_id, 'scheme_id': sid})
            if not existing:
                apps_col.insert_one({
                    'user_id': user_id, 'scheme_id': sid,
                    'status': 'eligible_not_applied',
                    'document_completeness': 0,
                    'benefit_probability': r['benefit_probability'],
                    'documents_uploaded': {},
                    'reminder_sent': False,
                    'created_at': datetime.now(timezone.utc),
                })

        # Update user location
        if user_id:
            get_collection('users').update_one(
                {'_id': ObjectId(user_id)} if len(user_id) == 24 else {'phone': user_id},
                {'$set': {
                    'state': responses.get('state', ''),
                    'district': responses.get('district', ''),
                    'village': responses.get('village', ''),
                }}
            )

        # Format results
        result_schemes = []
        for r in eligible:
            s = r['scheme']
            result_schemes.append({
                'scheme_id': s['scheme_id'],
                'name': s['name'].get(language, s['name']['en']),
                'description': s['description'].get(language, s['description']['en']),
                'category': s['category'],
                'benefit_amount': s['benefit_amount'],
                'last_date': s['last_date'],
                'required_documents': s['required_documents'],
                'match_score': r['eligibility']['match_score'],
                'is_full_match': r['eligibility']['eligible'],
                'is_partial': r['eligibility']['partial'],
                'benefit_probability': r['benefit_probability'],
                'reasons_met': r['eligibility']['reasons_met'],
                'reasons_not_met': r['eligibility']['reasons_not_met'],
            })

        request.session['eligible_schemes'] = result_schemes
        request.session['user_responses'] = responses

        return JsonResponse({
            'success': True,
            'total_eligible': len(result_schemes),
            'schemes': result_schemes,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def api_upload_document(request):
    try:
        scheme_id = request.POST.get('scheme_id')
        doc_type = request.POST.get('doc_type')
        user_id = request.session.get('user_id')
        file = request.FILES.get('document')

        if not all([scheme_id, doc_type, file]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        # Simulated verification (always pass for demo)
        verified = True
        apps_col = get_collection('applications')
        app = apps_col.find_one({'user_id': user_id, 'scheme_id': scheme_id})

        if app:
            docs = app.get('documents_uploaded', {})
            docs[doc_type] = {'uploaded': True, 'verified': verified, 'filename': file.name}

            # Find scheme to calculate completeness
            scheme = next((s for s in DUMMY_SCHEMES if s['scheme_id'] == scheme_id), None)
            completeness = 0
            if scheme:
                completeness = calculate_document_completeness(scheme['required_documents'], docs)

            apps_col.update_one(
                {'_id': app['_id']},
                {'$set': {
                    'documents_uploaded': docs,
                    'document_completeness': completeness,
                    'benefit_probability': completeness * 0.4 + 60,
                }}
            )

        return JsonResponse({
            'success': True, 'verified': verified,
            'doc_type': doc_type, 'completeness': completeness,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_locations(request):
    return JsonResponse({'locations': LOCATIONS})


@csrf_exempt
@require_POST
def api_ask_question(request):
    """
    Proxy to Flask AI service for dynamic questioning.
    Includes RULE-BASED answer validation (no AI).
    """
    try:
        data = json.loads(request.body)

        # ─── Rule-based answer validation (mandatory check) ───
        last_answer = data.get('last_answer')
        last_key = data.get('last_key')
        last_type = data.get('last_type')

        if last_answer is not None and last_key and last_type:
            validation = _validate_answer(last_answer, last_key, last_type, data)
            if not validation['valid']:
                return JsonResponse({
                    'done': False,
                    'validation_error': True,
                    'error_message': validation['message'],
                    'question': data.get('last_question', ''),
                    'key': last_key,
                    'type': last_type,
                    'options': data.get('last_options', []),
                })

        try:
            resp = requests.post(
                f"{settings.AI_SERVICE_URL}/ask",
                json=data, timeout=15
            )
            return JsonResponse(resp.json())
        except requests.exceptions.ConnectionError:
            # Fallback if Flask service is not running
            return _fallback_question(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _validate_answer(answer, key, answer_type, data):
    """
    RULE-BASED answer validation — no AI used.

    Checks:
    1. Answer is not empty or meaningless
    2. Number answers are valid numbers within expected range
    3. Yes/No answers match expected format
    4. Select answers match available options
    5. Text answers aren't gibberish or off-topic

    Returns: {'valid': bool, 'message': str}
    """
    answer = str(answer).strip()

    # Check empty
    if not answer:
        return {'valid': False, 'message': 'Please provide an answer. This field cannot be empty.'}

    # Check for obviously irrelevant/off-topic responses
    off_topic_patterns = [
        'hello', 'hi', 'hey', 'lol', 'haha', 'joke', 'funny', 'football',
        'cricket', 'movie', 'weather', 'politics', 'modi', 'rahul',
        'what is your name', 'who are you', 'shut up', 'stupid', 'idiot',
        "don't know", "i don't know", 'maybe', 'perhaps', 'whatever',
        'none of your business', 'why', 'how', 'tell me', 'help',
    ]
    answer_lower = answer.lower().strip()
    if answer_lower in off_topic_patterns or len(answer_lower) > 200:
        return {
            'valid': False,
            'message': 'This answer is out of context. Please provide a valid response.'
        }

    # Validate by type
    if answer_type == 'number':
        try:
            num = float(answer.replace(',', ''))
            if key == 'age' and (num < 0 or num > 130):
                return {'valid': False, 'message': 'Please enter a valid age between 0 and 130.'}
            if key == 'income' and num < 0:
                return {'valid': False, 'message': 'Income cannot be negative. Please enter a valid amount.'}
            if key == 'income' and num > 100000000:
                return {'valid': False, 'message': 'Please enter a realistic annual income amount.'}
        except (ValueError, TypeError):
            return {'valid': False, 'message': 'Please enter a valid number.'}

    elif answer_type == 'yesno':
        valid_yes = ['yes', 'no', 'y', 'n', 'हां', 'नहीं', 'हा', 'ना',
                     'ಹೌದು', 'ಇಲ್ಲ', 'అవును', 'కాదు', 'ஆம்', 'இல்லை',
                     'true', 'false', '1', '0']
        if answer_lower not in valid_yes:
            return {
                'valid': False,
                'message': 'Please answer with Yes or No only.'
            }

    elif answer_type == 'select':
        options = data.get('last_options', [])
        if options and answer_lower not in [str(o).lower() for o in options]:
            return {
                'valid': False,
                'message': f'Please select one of the given options: {", ".join(str(o) for o in options)}'
            }

    elif answer_type == 'text':
        # Text should be at least 2 chars and not just numbers/symbols
        if len(answer) < 2:
            return {'valid': False, 'message': 'Please provide a meaningful answer (at least 2 characters).'}
        if answer.isdigit():
            return {'valid': False, 'message': 'Please provide a text answer, not just numbers.'}

    return {'valid': True, 'message': 'OK'}


def _fallback_question(data):
    """Fallback question logic when Flask AI service is unavailable."""
    current = data.get('current_responses', {})
    lang = data.get('language', 'en')

    questions_flow = [
        {"key": "state", "en": "Which state do you live in?", "hi": "आप किस राज्य में रहते हैं?", "kn": "ನೀವು ಯಾವ ರಾಜ್ಯದಲ್ಲಿ ವಾಸಿಸುತ್ತೀರಿ?", "te": "మీరు ఏ రాష్ట్రంలో నివసిస్తున్నారు?", "ta": "நீங்கள் எந்த மாநிலத்தில் வசிக்கிறீர்கள்?", "type": "select", "options": list(LOCATIONS.keys())},
        {"key": "district", "en": "Which district?", "hi": "कौन सा जिला?", "kn": "ಯಾವ ಜಿಲ್ಲೆ?", "te": "ఏ జిల్లా?", "ta": "எந்த மாவட்டம்?", "type": "select", "options_from": "state"},
        {"key": "village", "en": "Which village?", "hi": "कौन सा गाँव?", "kn": "ಯಾವ ಗ್ರಾಮ?", "te": "ఏ గ్రామం?", "ta": "எந்த கிராமம்?", "type": "select", "options_from": "district"},
        {"key": "name_input", "en": "What is your name?", "hi": "आपका नाम क्या है?", "kn": "ನಿಮ್ಮ ಹೆಸರೇನು?", "te": "మీ పేరు ఏమిటి?", "ta": "உங்கள் பெயர் என்ன?", "type": "text"},
        {"key": "age", "en": "How old are you?", "hi": "आपकी उम्र क्या है?", "kn": "ನಿಮ್ಮ ವಯಸ್ಸು ಎಷ್ಟು?", "te": "మీ వయసు ఎంత?", "ta": "உங்கள் வயது என்ன?", "type": "number"},
        {"key": "gender", "en": "What is your gender?", "hi": "आपका लिंग?", "kn": "ನಿಮ್ಮ ಲಿಂಗ?", "te": "మీ లింగం?", "ta": "உங்கள் பாலினம்?", "type": "select", "options": ["male", "female", "other"]},
        {"key": "category", "en": "What is your social category?", "hi": "आपकी सामाजिक श्रेणी?", "kn": "ನಿಮ್ಮ ಸಾಮಾಜಿಕ ವರ್ಗ?", "te": "మీ సామాజిక వర్గం?", "ta": "உங்கள் சமூக வகை?", "type": "select", "options": ["General", "OBC", "SC", "ST"]},
        {"key": "occupation", "en": "What is your occupation?", "hi": "आपका व्यवसाय?", "kn": "ನಿಮ್ಮ ಉದ್ಯೋಗ?", "te": "మీ వృత్తి?", "ta": "உங்கள் தொழில்?", "type": "select", "options": ["farmer", "labourer", "self_employed", "student", "homemaker", "unemployed"]},
        {"key": "income", "en": "What is your annual family income?", "hi": "आपकी वार्षिक पारिवारिक आय?", "kn": "ನಿಮ್ಮ ವಾರ್ಷಿಕ ಕುಟುಂಬ ಆದಾಯ?", "te": "మీ వార్షిక కుటుంబ ఆదాయం?", "ta": "உங்கள் ஆண்டு குடும்ப வருமானம்?", "type": "number"},
        {"key": "has_land", "en": "Do you own agricultural land?", "hi": "क्या आपके पास कृषि भूमि है?", "kn": "ನಿಮ್ಮ ಬಳಿ ಕೃಷಿ ಭೂಮಿ ಇದೆಯೇ?", "te": "మీకు వ్యవసాయ భూమి ఉందా?", "ta": "உங்களுக்கு விவசாய நிலம் உள்ளதா?", "type": "yesno"},
        {"key": "bpl_card", "en": "Do you have a BPL card?", "hi": "क्या आपके पास बीपीएल कार्ड है?", "kn": "ನಿಮ್ಮ ಬಳಿ BPL ಕಾರ್ಡ್ ಇದೆಯೇ?", "te": "మీ వద్ద BPL కార్డ్ ఉందా?", "ta": "உங்களிடம் BPL அட்டை உள்ளதா?", "type": "yesno"},
        {"key": "disability", "en": "Do you have any disability (40% or more)?", "hi": "क्या आपको कोई विकलांगता है (40% या अधिक)?", "kn": "ನಿಮಗೆ ಯಾವುದೇ ಅಂಗವಿಕಲತೆ ಇದೆಯೇ (40% ಅಥವಾ ಹೆಚ್ಚು)?", "te": "మీకు ఏదైనా వైకల్యం ఉందా (40% లేదా అంతకంటే ఎక్కువ)?", "ta": "உங்களுக்கு ஏதேனும் இயலாமை உள்ளதா (40% அல்லது அதற்கு மேல்)?", "type": "yesno"},
    ]

    for q in questions_flow:
        if q["key"] not in current:
            # Handle dynamic options
            options = q.get("options", [])
            if q.get("options_from") == "state" and "state" in current:
                options = list(LOCATIONS.get(current["state"], {}).keys())
            elif q.get("options_from") == "district" and "state" in current and "district" in current:
                state_data = LOCATIONS.get(current["state"], {})
                options = state_data.get(current["district"], [])
            elif q.get("options_from") == "district" and "state" in current:
                options = list(LOCATIONS.get(current["state"], {}).keys())

            return JsonResponse({
                "done": False,
                "question": q.get(lang, q["en"]),
                "key": q["key"],
                "type": q["type"],
                "options": options,
            })

    return JsonResponse({"done": True, "message": "All questions answered"})


def api_schemes(request):
    lang = request.GET.get('lang', 'en')
    schemes = []
    for s in DUMMY_SCHEMES:
        schemes.append({
            'scheme_id': s['scheme_id'],
            'name': s['name'].get(lang, s['name']['en']),
            'description': s['description'].get(lang, s['description']['en']),
            'category': s['category'],
            'benefit_amount': s['benefit_amount'],
        })
    return JsonResponse({'schemes': schemes})


# ─── Admin Views ───

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'jansuvidha2026'


def admin_login(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            request.session['is_admin'] = True
            return redirect('admin_dashboard')
        error = 'Invalid credentials'
    return render(request, 'admin/login.html', {'error': error})


def admin_dashboard(request):
    if not request.session.get('is_admin'):
        return redirect('admin_login')
    return render(request, 'admin/dashboard.html')


def admin_logout(request):
    request.session.flush()
    return redirect('admin_login')


def api_admin_analytics(request):
    if not request.session.get('is_admin'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        state_filter = request.GET.get('state', '')
        district_filter = request.GET.get('district', '')
        village_filter = request.GET.get('village', '')

        apps_col = get_collection('applications')
        users_col = get_collection('users')

        # Build user filter
        user_filter = {}
        if state_filter:
            user_filter['state'] = state_filter
        if district_filter:
            user_filter['district'] = district_filter
        if village_filter:
            user_filter['village'] = village_filter

        if user_filter:
            matching_users = [str(u['_id']) for u in users_col.find(user_filter, {'_id': 1})]
            app_filter = {'user_id': {'$in': matching_users}}
        else:
            app_filter = {}

        all_apps = list(apps_col.find(app_filter))

        # Scheme-wise analytics
        scheme_stats = {}
        for app in all_apps:
            sid = app['scheme_id']
            if sid not in scheme_stats:
                scheme_name = sid
                for s in DUMMY_SCHEMES:
                    if s['scheme_id'] == sid:
                        scheme_name = s['name']['en']
                        break
                scheme_stats[sid] = {'name': scheme_name, 'eligible': 0, 'applied': 0, 'not_applied': 0}
            scheme_stats[sid]['eligible'] += 1
            if app['status'] == 'applied':
                scheme_stats[sid]['applied'] += 1
            else:
                scheme_stats[sid]['not_applied'] += 1

        # Location-wise analytics
        location_stats = {}
        all_users_with_apps = set(app.get('user_id') for app in all_apps)
        for uid in all_users_with_apps:
            try:
                user = users_col.find_one({'_id': ObjectId(uid)}) if len(str(uid)) == 24 else None
            except Exception:
                user = None
            if user:
                loc_key = f"{user.get('village', 'Unknown')}, {user.get('district', '')}"
                if loc_key not in location_stats:
                    location_stats[loc_key] = {
                        'village': user.get('village', 'Unknown'),
                        'district': user.get('district', ''),
                        'state': user.get('state', ''),
                        'eligible': 0, 'applied': 0,
                    }
                user_apps = [a for a in all_apps if a.get('user_id') == str(uid) or a.get('user_id') == uid]
                for a in user_apps:
                    location_stats[loc_key]['eligible'] += 1
                    if a['status'] == 'applied':
                        location_stats[loc_key]['applied'] += 1

        # Mark critical villages (eligible > 2x applied)
        critical_villages = []
        for loc_key, stats in location_stats.items():
            util_rate = (stats['applied'] / stats['eligible'] * 100) if stats['eligible'] > 0 else 0
            stats['utilization_rate'] = round(util_rate, 1)
            if stats['eligible'] > 0 and stats['applied'] < stats['eligible'] * 0.5:
                stats['is_critical'] = True
                critical_villages.append(stats)

        # Summary stats
        total_eligible = len(all_apps)
        total_applied = sum(1 for a in all_apps if a['status'] == 'applied')
        total_users = users_col.count_documents(user_filter) if user_filter else users_col.count_documents({})

        return JsonResponse({
            'summary': {
                'total_users': total_users,
                'total_eligible': total_eligible,
                'total_applied': total_applied,
                'total_not_applied': total_eligible - total_applied,
                'utilization_rate': round((total_applied / total_eligible * 100) if total_eligible > 0 else 0, 1),
            },
            'scheme_stats': list(scheme_stats.values()),
            'location_stats': list(location_stats.values()),
            'critical_villages': critical_villages,
            'locations': LOCATIONS,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def api_send_reminder(request):
    """
    Send SMS reminders to eligible-but-not-applied users.

    RULE-BASED LOGIC (No AI):
    1. Query MongoDB → find users with status='eligible_not_applied'
    2. Filter by village/district/state (optional)
    3. Send SMS via Fast2SMS API
    4. Log each attempt in 'sms_logs' collection
    5. Mark application as reminder_sent=True

    Trigger: Admin clicks "Send Reminders" OR cron job
    """
    if not request.session.get('is_admin'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        data = json.loads(request.body)
        target = data.get('target', 'all')
        village = data.get('village', None)
        district = data.get('district', None)
        state = data.get('state', None)

        # Import the reminder service (rule-based, no AI)
        from .reminder_service import send_reminder_to_eligible_users, get_sms_logs

        result = send_reminder_to_eligible_users(
            village=village if target == 'filtered' else None,
            district=district if target == 'filtered' else None,
            state=state if target == 'filtered' else None,
        )

        return JsonResponse({
            'success': True,
            'total_users': result.get('total_users', 0),
            'sms_sent': result.get('sms_sent', 0),
            'sms_simulated': result.get('sms_simulated', 0),
            'sms_failed': result.get('sms_failed', 0),
            'details': result.get('details', []),
            'message': result.get('message', 'Reminders processed.'),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_sms_logs(request):
    """Get recent SMS log entries for the admin dashboard."""
    if not request.session.get('is_admin'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        from .reminder_service import get_sms_logs
        logs = get_sms_logs(limit=30)
        return JsonResponse({'success': True, 'logs': logs})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

