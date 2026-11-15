# انتشار تأییدشده سها روی زیرساخت موجود

این تغییر هنوز روی سایت اصلی فعال نشده است. مسیر فعلی Compose و سرویس‌های app/db حفظ شده‌اند؛ سرور یا دیتابیس تازه‌ای ساخته نمی‌شود.

## مسیر هر نسخه

۱. Codex تغییر را روی شاخه جدا و PR آماده می‌کند. GitHub تست‌ها را روی SQLite، PostgreSQL و مرورگر اجرا و image را می‌سازد. تست کانتینری، ارتقا و بازگشت را با داده موقت بررسی می‌کند.
۲. نسخه آماده با SHA کامل و شماره اجرای CI گزارش می‌شود. تا تأیید صریح کاربر در گفت‌وگو با Codex، workflow انتشار اجرا نمی‌شود. ادغام PR برای آماده‌سازی نسخه نیز باید مجاز باشد؛ این تغییر فعلی هنوز ادغام نشده است.
۳. پس از تأیید، Codex فقط همان اجرای موفق CI روی main و همان SHA را dispatch می‌کند. workflow انتشار هیچ trigger از نوع push، PR یا workflow_run ندارد. artifact مربوط به PR، fork یا اجرای ناموفق برای انتشار پذیرفته نمی‌شود.
۴. GitHub-hosted runner بسته image را با SSH تأییدشده به سرور می‌فرستد. محدودیت SSH محیط Codex وارد مسیر انتشار نمی‌شود. سرور با `docker load` همان image را اجرا می‌کند؛ روی آروان build، pull از Docker Hub یا نصب وابستگی برنامه انجام نمی‌شود.
۵. اسکریپت موجود `server-update.sh --release`، صحت بسته، SHA، شناسه image، revision دیتابیس و فضای آزاد را بررسی می‌کند؛ سپس از PostgreSQL، آپلودها، `.env` و فایل‌های Compose پشتیبان محلی خصوصی می‌گیرد. فقط app تعویض می‌شود؛ db، volumeها، تنظیمات دامنه و `.env` جایگزین نمی‌شوند.
۶. سلامت و APIهای عمومی تست می‌شوند. فایل‌های ثابت Pages از **همان image** استخراج و سپس منتشر می‌شوند. فایل عمومی `release.json` نیز باید از دامنه اصلی همان شناسه image را برگرداند؛ کش CDN یا origin نادرست باعث موفقیت کاذب انتشار نمی‌شود. شکست سلامت، image قبلی را برمی‌گرداند؛ شکست مرحله انتشار فایل‌های ثابت نیز تلاش برای بازگرداندن image و سایت ثابت قبلی را فعال می‌کند.

## جلوگیری از انتشار بدون تأیید

در تنظیم فعلی مخزن، Pages از main به‌طور خودکار منتشر می‌شود. قبل از فعال‌سازی این سامانه، Source در **Settings → Pages → Build and deployment** باید روی **GitHub Actions** قرار گیرد. workflow پیش از تغییر سرور، این تنظیم را بررسی و در صورت legacy بودن متوقف می‌شود. تنظیم فعلی بدون اجازه کاربر تغییر داده نشده است.

تأیید از طریق گفت‌وگو با Codex انتخاب شده، نه تأیید دوم با دکمه GitHub. ثبت workflow_dispatch و عبارت دقیق `DEPLOY <SHA>` یا `ROLLBACK <image ID>` در GitHub باقی می‌ماند. کاربران دارای دسترسی اجرای workflow نیز می‌توانند آن را دستی اجرا کنند؛ تغییر خودکار در main به‌تنهایی اجازه انتشار نمی‌دهد. هیچ job محیط PR به کلید انتشار دسترسی ندارد.

## راه‌اندازی یک‌باره؛ فقط پس از تأیید مالک

پیش‌نیازها همان سرور فعلی‌اند: Docker Compose، systemd، Python 3.8+، SSH روی پورت ۲۲ و معماری amd64. GitHub runner باید بتواند به SSH سرور متصل شود. دسترسی به GitHub و سرویس artifact از runner میزبانی‌شده GitHub لازم است؛ سرور آروان برای دریافت image به Docker Hub نیاز ندارد. امکان اتصال GitHub-hosted runner به این سرور هنوز بدون کلید نصب‌شده قابل تأیید نیست.

۱. بعد از بازبینی و ادغام PR با تأیید کاربر، در Termius داخل پوشه همان پروژه:

```bash
git fetch origin main &&
setup_dir="$(mktemp -d /tmp/saha-deploy-setup.XXXXXX)" &&
git archive origin/main scripts/server-update.sh scripts/deploy_release.py scripts/deploy_receiver.py scripts/install-deploy-access.sh | tar -x -C "$setup_dir" &&
bash "$setup_dir/scripts/install-deploy-access.sh" "$(git rev-parse --show-toplevel)"
```

این نصب app/db/web را restart نمی‌کند. کد دریافت انتشار را در `/opt/saha-deploy` می‌گذارد و یک کلید جدید مخصوص انتشار با forced command، بدون shell عمومی، PTY یا forwarding به authorized_keys اضافه می‌کند؛ کلیدهای قبلی حفظ می‌شوند. تنظیمات استقرار موجود بازنویسی نمی‌شوند. نصب مجدد در مسیر متفاوت متوقف می‌شود.

۲. در **GitHub → Settings → Secrets and variables → Actions → Repository secrets** فقط این دو مقدار را وارد کنید:

| نام Secret | فایل روی سرور |
|---|---|
| `ARVAN_SSH_KEY` | محتوای `/root/.ssh/saha-actions-deploy` |
| `ARVAN_KNOWN_HOSTS` | محتوای `/opt/saha-deploy/github-known-hosts` |

کلید خصوصی را در چت، Git، اسکرین‌شات یا خروجی CI نفرستید. Secret اول کلید مخصوص انتشار است، نه کلید ورود شخصی Termius. Secret دوم کلید عمومی میزبان واقعی است؛ تطبیق میزبان در SSH اجباری است و `StrictHostKeyChecking` خاموش نمی‌شود. کلید انتشار دسترسی Docker/انتشار دارد و باید مانند دسترسی مدیریتی محافظت شود.

بعد از فعال‌سازی، `/release.json` باید از Pages/نسخه منتشرشده روی دامنه اصلی قابل دریافت باشد؛ اگر CDN آن را cache یا به origin دیگری هدایت کند، انتشار تأیید نمی‌شود و باید مسیردهی یا کش آن اصلاح شود.

متغیرهای اختیاری `ARVAN_HOST`، `ARVAN_USER` و `ARVAN_PORT` پیش‌فرض‌های تأییدشده `37.32.39.8`، `root` و `22` را دارند. در صورت تغییر میزبان یا پورت، known_hosts هم باید به‌صورت معتبر اصلاح شود. لازم نیست رمز PostgreSQL یا ADMIN_API_TOKEN را در GitHub بگذارید؛ این مقادیر همان `.env` خصوصی موجود می‌مانند.

۳. Source مربوط به Pages را طبق بخش قبل به GitHub Actions تغییر دهید. سپس Codex می‌تواند ابتدا عملیات فقط‌خواندنی `status` را اجرا و اتصال را بررسی کند؛ این عملیات app یا داده‌ها را عوض نمی‌کند. اولین انتشار واقعی همچنان به تأیید صریح شما نیاز دارد.

API مدیریت secrets/runners با دسترسی اتصال فعلی Codex محدود است؛ مقداردهی Secretها به مالک نیاز دارد. Codex اکنون هیچ کلیدی ندارد و هیچ تنظیم تولیدی را تغییر نداده است.

## فرمان‌های Codex پس از فعال‌سازی

خواندن وضعیت، بدون تغییر سایت:

```bash
gh workflow run deploy.yml --ref main -f operation=status
```

انتشار **فقط پس از تأیید همان نسخه در گفت‌وگو**:

```bash
gh workflow run deploy.yml --ref main \
  -f operation=deploy \
  -f revision=FULL_APPROVED_COMMIT_SHA \
  -f build_run_id=SUCCESSFUL_MAIN_CI_RUN_ID \
  -f confirmation="DEPLOY FULL_APPROVED_COMMIT_SHA"
```

Codex باید پیش از dispatch، نتیجه CI و SHA را نشان دهد و بعد از آن نتیجه workflow، وضعیت سرور و انتشار Pages را بررسی کند. اگر اجازه dispatch برای اتصال فعلی GitHub داده نشده باشد، مالک می‌تواند همین workflow را از Actions اجرا کند؛ نباید token یا کلید در چت وارد شود.

بازگشت دستی پس از خواندن وضعیت و تأیید image قبلی:

```bash
gh workflow run deploy.yml --ref main \
  -f operation=rollback \
  -f revision=sha256:APPROVED_PREVIOUS_IMAGE_ID \
  -f confirmation="ROLLBACK sha256:APPROVED_PREVIOUS_IMAGE_ID"
```

## حفظ داده و حدود بازگشت

- قفل مشترک سمت سرور و concurrency در GitHub جلوی دو ارتقای هم‌زمان از این مسیر را می‌گیرند. یک انتشار جای انتشار در حال اجرا را لغو نمی‌کند.
- state و overlay اجرایی داخل `.deploy/` خصوصی هستند. image قبلی با tag نگهداری می‌شود؛ پاک‌سازی خودکار image یا بکاپ نداریم. بکاپ‌ها روی همان سرورند؛ کپی خارج از سرور همچنان مسئولیت عملیاتی جداگانه است.
- rollback فقط image و فایل‌های ثابت نسخه قبلی را برمی‌گرداند. **دیتابیس و آپلودهای زنده از بکاپ جایگزین نمی‌شوند**؛ رزروها و عکس‌های ثبت‌شده بعد از بکاپ حفظ می‌شوند. بازیابی فاجعه از بکاپ، عملیات جدا و نیازمند تصمیم مالک و تطبیق داده‌های جدید است.
- انتشار عادی فقط وقتی مجاز است که revision دیتابیس در image جدید، image فعلی و دیتابیس زنده یکسان باشد. تغییر schema نیاز به طرح migration و بازگشتِ سازگار و تأیید جداگانه دارد؛ این مرحله عمداً خودکار و پنهانی انجام نمی‌شود.
- transaction سمت سرور زیر systemd اجرا می‌شود تا قطع اتصال SSH به‌تنهایی آن را متوقف نکند. قطع برق یا خرابی کامل میزبان ممکن است بررسی status و بازیابی صریح image سالم را لازم کند. state قبل از تعویض image نوشته می‌شود؛ انتشار بعدی روی state ناقص متوقف می‌شود.
- اگر تحویل SSH یا دریافت گزارش مبهم شد، Codex باید ابتدا status بخواند؛ اجرای دوباره یا ادعای انتشار موفق بدون بررسی مجاز نیست.
- rollback بعد از ۱۴ روز هم به artifact GitHub وابسته نیست؛ image قبلی و سایت داخل آن روی سرور حفظ می‌شوند. برای انتشار عادی پس از انقضای artifact، CI باید یک نسخه main را دوباره آماده کند؛ بازگرداندن کد قدیمی‌تر از نسخه قبلی می‌تواند با commit بازگردانی و CI جدید انجام شود.

## تست‌های انجام‌شده و تکرارپذیر

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
bash -n scripts/server-update.sh scripts/install-deploy-access.sh scripts/approved_transport.sh
```

تست یکپارچه Docker/PG تنها روی پروژه و volumeهای موقت با نام تصادفی اجرا می‌شود:

```bash
SAHA_RUN_DOCKER_DEPLOY_TEST=1 \
SAHA_TEST_IMAGE_COMMIT=SHA_OF_LOCALLY_BUILT_TEST_IMAGE \
.venv/bin/python tests/release_container_test.py
```

این تست، انتشار موفق، rollback دستی، rollback پس از خرابی سلامت، حفظ رزرو واقعی آزمایشی، حفظ فایل عکس و حفظ `.env` را بررسی می‌کند و فقط volumeهای تازه همان تست را پاک می‌کند. هیچ تستی به سرور اصلی متصل نمی‌شود. تست‌های CI قبل از انتشار نیازمند موفقیت همه این بررسی‌ها هستند.

## تشخیص خطای دریافت Secret

Repository Secretها هنگام صف‌شدن workflow خوانده می‌شوند؛ پس از ثبت یا اصلاح دسترسی آن‌ها، یک اجرای **جدید** با operation=status آغاز کنید. پیام اجرای قدیمی اثبات نمی‌کند که Secretهای فعلی وجود ندارند. نگاشت Secretها در مرحله انتقال مستقیم از `${{ secrets.ARVAN_SSH_KEY }}` و `${{ secrets.ARVAN_KNOWN_HOSTS }}` است؛ نیازی به `secrets: inherit` برای این workflow غیرقابل‌استفاده‌مجدد نیست. مجوزهای GITHUB_TOKEN نیز جایگزین یا محدودکننده این نگاشت نیستند.

کلید پیش از SSH در فایل موقت runner بررسی می‌شود. پایان‌خط CRLF، متن دارای `\n`، کوتیشن، فاصله و wrapper متنی base64 در همان فایل موقت استاندارد می‌شوند. نوع قالب اصلاح‌شده، بدون محتوا، طول، اثرانگشت یا بخش‌هایی از Secret گزارش می‌شود. خود Repository Secretها تغییر نمی‌کنند. فایل کلید موقت دسترسی ۶۰۰ دارد و پس از مرحله پاک می‌شود. اگر مقدار واقعاً کلید عمومی، رمزدار یا ناقص باشد، اجرا با پیام مشخص متوقف می‌شود؛ برنامه هیچ کلید جدیدی تولید نمی‌کند و بررسی کلید میزبان را خاموش نمی‌کند.

اگر مقدار دو Secret به‌وضوح جابه‌جا وارد شده باشد (داده known_hosts در فیلد کلید و یک کلید خصوصی قابل‌اعتبارسنجی در فیلد میزبان)، runner فقط binding فایل‌های موقت را اصلاح و این وضعیت را بدون چاپ محتوا گزارش می‌کند؛ نام و مقدار Secretهای ذخیره‌شده تغییر نمی‌کنند. تطبیق کلید میزبان همچنان اجباری است و ورودی مبهم یا نامعتبر رد می‌شود.
