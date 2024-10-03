# import json
# import re
# import os
# import datefinder
# import dateparser
# from datetime import datetime
# import nltk
# from app.util.database import LocalStorage
# from nltk.sentiment import SentimentIntensityAnalyzer
# from nltk.tokenize import word_tokenize
# from nltk.corpus import stopwords
# from nltk.stem import WordNetLemmatizer
# from collections import Counter
# import string

# resources = [
#     'vader_lexicon',
#     'punkt',
#     'stopwords',
#     'wordnet'
# ]

# for resource in resources:
#     nltk.download(resource)

# def get_nltk_language(language_code):
#     language_mapping = {
#         "arb": "arabic",
#         "ar-AE": "arabic",
#         "ca-ES": "catalan",
#         "yue-CN": "cantonese",
#         "cmn-CN": "mandarin",
#         "da-DK": "danish",
#         "nl-BE": "dutch",
#         "nl-NL": "dutch",
#         "en-AU": "english",
#         "en-GB": "english",
#         "en-IN": "english",
#         "en-NZ": "english",
#         "en-ZA": "english",
#         "en-US": "english",
#         "en-GB-WLS": "english",
#         "fi-FI": "finnish",
#         "fr-FR": "french",
#         "fr-BE": "french",
#         "fr-CA": "french",
#         "hi-IN": "hindi",
#         "de-DE": "german",
#         "de-AT": "german",
#         "is-IS": "icelandic",
#         "it-IT": "italian",
#         "ja-JP": "japanese",
#         "ko-KR": "korean",
#         "nb-NO": "norwegian",
#         "pl-PL": "polish",
#         "pt-BR": "portuguese",
#         "pt-PT": "portuguese",
#         "ro-RO": "romanian",
#         "ru-RU": "russian",
#         "es-ES": "spanish",
#         "es-MX": "spanish",
#         "es-US": "spanish",
#         "sv-SE": "swedish",
#         "tr-TR": "turkish",
#         "cy-GB": "welsh"
#     }

#     return language_mapping.get(language_code, "english")

# def extract_dates(text):
#     dates = list(datefinder.find_dates(text))
#     if not dates:
#         date_patterns = [
#             r'\b\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}\b',  # Matches 01/01/2020, 01-01-2020
#             r'\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{2,4}\b',  # Matches 01 Jan 2020
#             r'\b(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{2,4}\b'  # Matches January 1, 2020
#         ]
        
#         for pattern in date_patterns:
#             matches = re.findall(pattern, text)
#             for match in matches:
#                 try:
#                     dates.append(datetime.strptime(match, "%d/%m/%Y"))
#                 except ValueError:
#                     try:
#                         dates.append(datetime.strptime(match, "%d-%m-%Y"))
#                     except ValueError:
#                         try:
#                             dates.append(datetime.strptime(match, "%d %b %Y"))
#                         except ValueError:
#                             try:
#                                 dates.append(datetime.strptime(match, "%B %d, %Y"))
#                             except ValueError:
#                                 continue
        
#         if len(dates) == 0:
#             # TODO: need to replace/add spanish words in below regex to make it compaitible with spanish language
#             date_keywords = re.findall(r'\b(today|tomorrow|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|next week|in \d+ days|in \d+ weeks)\b', text, re.IGNORECASE)
#             for keyword in date_keywords:
#                 parsed_date = dateparser.parse(keyword)
#                 if parsed_date:
#                     dates.append(parsed_date)

#     return dates

# def preprocess(text, lang):
#     lang = get_nltk_language(lang)
#     stop_words = set(stopwords.words(lang))
#     lemmatizer = WordNetLemmatizer()
#     tokens = word_tokenize(text)
#     tokens = [word.lower() for word in tokens if word.isalpha()]
#     tokens = [lemmatizer.lemmatize(word) for word in tokens if word not in stop_words]
    
#     return tokens

# def isAnnoying(messages):
#     sia = SentimentIntensityAnalyzer()
#     scores = [ sia.polarity_scores(m)["compound"] for m in messages ]
#     if len(scores) > 0:
#         return (sum(scores)/len(scores)) <= -0.45
#     return 0

# def keyword_matching(text, keywords, lang):
#     tokens = preprocess(text, lang)
#     token_set = set(tokens)

#     return not token_set.isdisjoint(keywords)

# def context_matching(text, keywords, lang):
#     tokens = preprocess(text, lang)
#     counter = Counter(tokens)
    
#     keyword_count = sum(counter[keyword] for keyword in keywords if keyword in counter)
    
#     return keyword_count > 0

# def Run(call, config):
#     """
#     Friendly Name: Call Tager

#     Description:
#     This is a addon hook to tag the call once a call is finished. There are 7 unique tags, and this addon will mark the call with best suitable tag.

#     Hook Type: POST_CALL

#     Logo URL: https://example.com/logo.png
#     """
#     if call.callStatus == "AMD":
#         call.callStatus = "BUZON"
#     elif call.callDuration < 60:
#         call.callStatus = "RECOVER"
#     else:
#         chat = json.loads(call.callScript)
#         chat = [ m["dialog"] for m in chat if m['role'] == "CUSTOMER" ]

#         schedule_keywords = {"schedule", "call", "reschedule", "time", "date", "afternoon", "tomorrow"}

#         if isAnnoying(chat):
#             call.callStatus = "ANNOYING"
#         elif keyword_matching("\n".join(chat), schedule_keywords, config["language"]) or context_matching("\n".join(chat), schedule_keywords, config["language"]):
#             call.callStatus = "AGENDA"
#         else:
#             dates = extract_dates("\n".join(chat))
#             if len(dates) > 0:
#                 call.callStatus = "PROMISE ({})".format(dates[0].strftime("%Y-%m-%d"))
    
#     if call.isDirty:
#         ls = LocalStorage()
#         ls.Update(call)
#         return True
#     return False