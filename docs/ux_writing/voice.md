# Talent Search voice (Persian)

Version 1, 2026-10-11. Built from eot.ir (read-only, `eot_vps text`), the project copy rules in
`.claude/agents/ts-ux-writer.md`, and the 2026-10-11 UX audit. Owner decisions override this file.

Talent Search speaks as part of the EOT family: the same institute, the same restraint, a younger and more
practical register. eot.ir is the elder sibling: scholarly, careful about limits, warm without selling.
We keep its honesty and its "know the limit" habit, and drop its academic officialese.

**Counseling, never therapy (owner decision 2026-10-11).** Talent Search speaks the language of counseling, never of
therapy or medicine. Nothing a user sees (site, product, back office, SMS) says «درمان»، «درمانگر»، «روان‌درمانی»،
«بیمار»/«مریض»، «بالینی»، «کلینیک»/«درمانگاه» (English: therapy, treatment, patient, clinic, clinical). Write «مشاوره»،
«جلسهٔ مشاوره»، «مشاور»، «مرکز مشاوره»، «مراجع» (counseling-center panels only). «درماندگی» and «درمانده» (helplessness)
are ordinary psychological words and stay. Terms: glossary §2-§4.

## 1. Sources read on eot.ir (2026-10-11)

| Page | Path | What it taught |
|---|---|---|
| Home | `/` | Mission line, service map, «قدرت گرفته از هیجان اندیشه», the testing centre is called «استعدادیاب» |
| About | `/about` | Institute self-description, «روان‌شناسی تعاملی», trust block (registration numbers) |
| Services map | `/خدمات` | Need-first navigation: «به‌جای شناخت نام خدمات، از نیاز خودتان شروع کنید.» |
| Assessments | `/آزمون-روانشناسی` | Words for instruments: آزمون، ارزیابی، فهرست، گویه، ابعاد سنجش، خودسنجی؛ "not a diagnosis" note |
| Method | `/روش-ارزیابی-و-تفسیر` | How a level is read: «نباید به‌طور خودکار با «بد»، «متوسط» یا «خوب» یکی گرفته شوند.» |
| Online counselling | `/مشاوره-روانشناسی-آنلاین` | 3-step "how it works", exact prices, honest "may change" note |
| Group classes | `/کلاس-گروهی-آنلاین` | Course cards, «لینک جلسه … ارسال می‌شود», 3-step process |
| Internship (course) | `/کارورزی-روانشناسی-آنلاین` | Long programme page, professional audience |
| FAQ | `/سوالات-متداول` | Questions in the reader's own words: «اگر ندانم از کدام خدمت شروع کنم چه کار کنم؟» |
| Psychological safety | `/ایمنی-روانشناختی` | Crisis wording, «خودسنجی با تشخیص متفاوت است» |
| Privacy | `/حریم-خصوصی` | Data categories, minors, retention |
| Contact | `/contactus` | Form, routing to the right service, emergency note |
| Articles (5) | `/blog/46/1977`, `1976`, `1983`, `1941`, `1938`, `1945` | Dr. Kazemi's essay voice: definitions, contrasts, Persian proverbs, Arabic quotations, heavy officialese |

Not readable: `/blog/46/1959` (404 by numeric URL), `/slides` (404, eLearning not on this path).

## 2. Audiences and register

| Audience | Who | Pronoun | Register | What they need first |
|---|---|---|---|---|
| Student (15–18) | takes an instrument by invitation or alone | «تو» | warm, short, concrete, never childish | what this is, how long, who sees it, that they can stop |
| Adult participant | job applicant, client, self-tester | «شما» | plain, respectful, calm | effort, privacy, what the result is and is not |
| Parent / ولی | consents for a minor, reads a child's result | «شما» | reassuring, exact, no jargon | what the child will do, who sees what, how to withdraw |
| School principal / counselor | runs an education panel | «شما» | collegial, practical | invite a class, see who finished, what they may see |
| Counseling-center director / counselor («مدیر مرکز مشاوره» / «مشاور مرکز») | runs a counseling-center panel | «شما» | professional, precise, no hype | verification, access limits, the counselor guide («راهنمای مشاور») |
| HR / hiring manager / reviewer | runs an employment panel | «شما» | business-plain, legally careful | what is shown (bands only), fairness, consent |
| Platform staff (Odoo backend) | EOT team | «شما» | terse, technical allowed | exact state names |

One page, one audience, one pronoun. A page that serves two audiences (the player when a parent answers about a child)
picks the person holding the device.

## 3. Tone principles

Each principle has a real eot.ir sentence as evidence, then a do/don't pair for our product. A few evidence quotes
contain eot.ir's own words «ارزیابی بالینی»، «درمانگر»، «مرکز درمانی»; they are quoted verbatim as evidence of tone only.
Our copy uses the counseling words above.

### 3.1 Start from the reader's need, not from our menu
Evidence (`/خدمات`): «به‌جای شناخت نام خدمات، از نیاز خودتان شروع کنید.»
Also: «مسئله‌ای دارم که می‌خواهم با روان‌شناس یا مشاور بررسی کنم.» (need written in the first person)
- Do: «می‌خواهم کلاسم را دعوت کنم» → button «ارسال دعوت گروهی»
- Don't: «ماژول دعوت گروهی» / «مدیریت کمپین‌ها»

### 3.2 Say the limit plainly, once, in the right place
Evidence (`/آزمون-روانشناسی`): «نتیجه آن‌ها به‌تنهایی جایگزین تشخیص، ارزیابی بالینی یا مشاوره تخصصی روان‌شناس و پزشک نیست.»
And (`/ایمنی-روانشناختی`): «خودسنجی با تشخیص متفاوت است».
- Do: «این نتیجه تصویری از پاسخ‌های تو در همین سنجه است، نه تشخیص.»
- Don't: repeat a disclaimer on every card, or hide it in the footer only.

### 3.3 Levels are not verdicts
Evidence (`/روش-ارزیابی-و-تفسیر`): «این سطح‌ها طبقه‌های امتیاز همان ابزار هستند و نباید به‌طور خودکار با «بد»، «متوسط» یا «خوب» یکی گرفته شوند.»
- Do: «سطح: بالا» with the factor's definition beside it.
- Don't: «عالی»، «ضعیف»، «نمرهٔ شما خوب نیست».

### 3.4 Exact facts beat adjectives
Evidence (`/مشاوره-روانشناسی-آنلاین`): «جلسه عمومی مشاوره آنلاین در حال حاضر ۴۵ دقیقه است و هزینه آن … ۸۸۰٬۰۰۰ تومان نمایش داده می‌شود.»
Also the stat strip on `/`: «۲۰ کتاب و اثر بلند»، «۱۴۲ مقاله منتشرشده»، «۴ دهه تجربه علمی و حرفه‌ای».
- Do: «۱۵ جمله برای هر زمینه؛ حدود ۲ دقیقه برای هر زمینه.»
- Don't: «سریع و دقیق‌ترین آزمون استعداد».

### 3.5 Three steps, each a verb
Evidence (`/مشاوره-روانشناسی-آنلاین`): «درمانگر را انتخاب کنید» · «روز و ساعت را ببینید» · «رزرو را تکمیل کنید».
Also (`/کلاس-گروهی-آنلاین`): «کلاس مناسب را انتخاب کنید» · «ثبت‌نام آنلاین را کامل کنید» · «آنلاین در جلسه حاضر شوید».
- Do: «پیوند را بفرستید» · «شاگردان پاسخ می‌دهند» · «نتیجه‌ها را ببینید»
- Don't: «فرایند ایجاد دعوت و اقدام به ارسال آن توسط کاربر».

### 3.6 Safety first, without alarm
Evidence (footer, every page): «در وضعیت اضطراری منتظر نوبت نمانید: اورژانس اجتماعی ۱۲۳».
And (`/ایمنی-روانشناختی`): «از خدمات اضطراری محل خود، نزدیک‌ترین مرکز درمانی یا یک فرد قابل اعتماد که می‌تواند کنار شما باشد کمک بگیرید.»
- Do: short imperative, a number in Persian digits, no adjectives: «اگر حالت خوب نیست، منتظر نمان: ۱۲۳.»
- Don't: «متأسفانه این سامانه برای موارد اورژانسی طراحی نگردیده است!»

### 3.7 Honest about what is not ready
Evidence (`/`): «سایت مدرسه استعداد در حال راه‌اندازی است». Assessment cards: «شروع آنلاین به‌زودی».
And (`/مشاوره-روانشناسی-آنلاین`): «هزینه و زمان جلسه ممکن است در آینده تغییر کند؛ مبلغ و زمان نهایی همان اطلاعاتی است که هنگام رزرو … نمایش داده می‌شود.»
- Do: «پرداخت آنلاین هنوز راه نیفتاده است؛ تا آن زمان دعوت‌ها رایگان است.»
- Don't: a disabled button with no explanation, or «به‌زودی!!».

### 3.8 Route, don't block
Evidence (`/contactus`): «اگر موضوع شما به یکی از خدمات مشخص مربوط است، از مسیر مستقیم همان خدمت استفاده کنید؛ برای سایر موضوعات، پیام خود را از فرم تماس برای ما بفرستید.»
- Do (error): «این پیوند دیگر باز نیست. از کسی که آن را فرستاده بخواه پیوند تازه بفرستد.»
- Don't: «دسترسی غیرمجاز» and nothing else.

### 3.9 Warm, never flattering
Evidence (`/about`): «مسیر مناسب خودتان را از همین‌جا شروع کنید. می‌توانید با مطالعه یک مفهوم، انجام یک ارزیابی، ورود به یک دوره آموزشی یا گفت‌وگو با یک متخصص شروع کنید.»
- Do: «خوش آمدی. این کار حدود ۱۵ دقیقه طول می‌کشد و هر وقت بخواهی می‌توانی دست نگه داری.»
- Don't: «تبریک! شما یک استعداد درخشان هستید.» (also a forbidden talent claim)

### 3.10 Define before you use
Evidence (article «نکات اساسی پرورش تیزهوش در خانواده»): «هوش، توانایی یادگیری است.» / «هوش با عقل، متفاوت است.»
Short declarative definitions are the house habit. Use them for every product term the first time a reader meets it.
- Do: «پنل فضای مدرسهٔ شما در تلنت سرچ است؛ از اینجا شاگردان را دعوت می‌کنید.»
- Don't: drop «پنل»، «سنجه» or «دفتر ممیزی» on a newcomer with no gloss.

### 3.11 Trust through named people and numbers, not slogans
Evidence (`/about`): «مؤسسه تعاملی هیجان اندیشه (شماره ثبت ۴۵۴۷۷) … مرکز خدمات روانشناسی ایران‌اندیش (شماره نظام ۳۲۷)».
Also (`/مشاوره-روانشناسی-آنلاین`): «روان‌شناسانی که پیش از رزرو، نامشان را می‌بینید» (home).
- Do: «سنجه‌ها بر پایهٔ پژوهش‌های دکتر ناصرالدّین کاظمی حقیقی ساخته شده‌اند.»
- Don't: «مورد اعتماد هزاران نفر» without a source.

### 3.12 Plain Persian over academic Persian (where we differ from eot.ir)
eot.ir articles carry the officialese we must not copy:
«دلالت‌های این تحقیقات را مورد بررس[ی] قرار می‌دهیم»، «از استعداد خاص برخوردار می‌باشد»، «تأسیس گردید»، «علی‌رغم».
The newer eot.ir service pages already moved toward plain Persian («هر ارزیابی مستقیماً در مرورگر انجام می‌شود»). We
follow the service pages, never the article register.
- Do: «بررسی می‌کنیم»، «استعداد خاصی دارد»، «تأسیس شد»، «با وجود».
- Don't: «مورد بررسی قرار می‌گیرد»، «برخوردار می‌باشد»، «گردید»، «علی‌رغم».

## 4. Officialese and calque replacement list

| Avoid | Write | Note |
|---|---|---|
| می‌باشد / می‌باشند | است / هستند | |
| گردید / گردیده است | شد / شده است | eot.ir about: «تأسیس گردید» |
| جهت (= برای) | برای | «جهت» only for direction |
| به منظورِ / در راستای | برای | |
| اقدام به ارسال نمایید | بفرستید | direct verb |
| نمایید / بفرمایید | کنید | |
| مورد بررسی قرار دادن | بررسی کردن | eot.ir articles |
| از … برخوردار بودن | … داشتن | «از مهارت اجتماعی بیشتری برخوردارند» → «مهارت اجتماعی بیشتری دارند» |
| لازم به ذکر است | (delete; say the thing) | |
| به شما کمک می‌کند تا … | با این … می‌توانید … | calque of "helps you to" |
| در حال حاضر امکان‌پذیر نیست | فعلاً نمی‌شود / هنوز … نشده است | |
| توسط (agent in passive) | active sentence | «توسط مدیر حذف شد» → «مدیر پنل آن را حذف کرد» |
| علی‌رغم | با وجود / با اینکه | |
| کلیه / تمامی | همهٔ | |
| متأسفانه | (delete; say what happened and what to do) | project rule |
| لطفاً … | imperative alone, or «… کن/کنید» | keep «لطفاً» out of errors; at most once in a long form |
| ! | . | project rule |
| تخصیص دادن | سپردن / مسئول کردن | see glossary |
| کاربر گرامی | (delete; start with the message) | |
| موفقیت‌آمیز بود | name the result: «دعوت فرستاده شد.» | |
| اطلاعات با موفقیت ثبت گردید | «ذخیره شد.» | |
| آیا مطمئن هستید؟ | name what will be lost: «۱۲ دعوت باز بسته می‌شود.» | destructive confirmations |
| لاگ / پروفایل / کمپین / داشبورد (in prose) | دفتر ممیزی / نمایه / دعوت گروهی / پیشخوان (see glossary) | |
| Latin digits in text (115) | ۱۱۵ | codes, phones, emails, URLs stay Latin in `<bdi dir="ltr">` |

Spacing (دستور خط فرهنگستان): نیم‌فاصله in «می‌»، «نمی‌»، «‌ها»، «‌ای»، «‌تر/‌ترین»، compound words («شرکت‌کننده»، «تکمیل‌شده»);
«ـهٔ» for ezafe after silent ه in headings and labels («نتیجهٔ»، «دربارهٔ»), consistently, as the product already does
(«نتیجهٔ» ۴۰، «نتیجه‌ی» ۰).

## 5. How literature shapes tone (and never appears)

Owner decision 2026-10-11: no poems, no quoted lines, no allusions anywhere on the site or in the product.
eot.ir articles do quote (Arabic hadith, Persian verse, the proverb «گلیم خود را از آب بیرون بکشد»); Talent Search does not.

What we take from Saadi's Golestan and Hafez is only how sentences behave:
- «سهل و ممتنع»: a sentence a 15-year-old reads once and understands, that an editor cannot shorten. Test: can a word go?
- Short clauses, verb at the end, the important word just before the verb: «نتیجه را فقط خودت می‌بینی.»
- Balance and contrast in pairs, the way eot.ir defines things: «خودسنجی برای شناخت مفید است، اما تشخیص نیست.»
- Dignity without distance: address the reader as an equal; never «کاربر گرامی», never baby talk to students.
- Warmth through care for the reader's situation, not through compliments.
- Rhythm: read the sentence aloud. If it needs a breath in the middle, split it.

## 6. Quick checks before handing over a string

1. Right pronoun for this page's audience? One pronoun per page?
2. Every concept uses the glossary term?
3. No «متأسفانه», no «!», no unprovable superlative, no talent/diagnosis promise?
4. Officialese list clean? نیم‌فاصله correct? Persian digits?
5. Buttons verb-first, naming the outcome? Errors: what happened, why, what now?
6. Consent/privacy readable by a 15-year-old? Any change there is `owner_decision`.
7. Assessment statements, scoring labels, the book's interpretation texts untouched?
8. No therapy or medical word (درمان، درمانگر، بیمار، بالینی، کلینیک)? Counseling words instead.
