#!/bin/bash

# ===================================================================
#  سكريبت التثبيت والتشغيل التلقائي لبوت الإبلاغ
# ===================================================================
#  يقوم بـ:
#  1. تثبيت المتطلبات الأساسية
#  2. تثبيت مكتبات Python
#  3. تشغيل ملف add.py
#  4. تشغيل ملف khayal.py
# ===================================================================

# ألوان للنصوص
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# دالة طباعة الرسائل
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# دالة فحص وجود الأمر
check_command() {
    if command -v $1 &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# دالة فحص وجود ملف
check_file() {
    if [ -f "$1" ]; then
        return 0
    else
        return 1
    fi
}

# دالة فحص وجود مجلد
check_directory() {
    if [ -d "$1" ]; then
        return 0
    else
        return 1
    fi
}

# ===================================================================
#  بداية السكريبت
# ===================================================================

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                بوت الإبلاغ - سكريبت التثبيت التلقائي        ║"
echo "║                    Telegram Report Bot                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

print_status "بدء عملية التثبيت والتشغيل..."

# ===================================================================
#  الخطوة 1: فحص النظام والمتطلبات الأساسية
# ===================================================================

print_status "الخطوة 1/5: فحص النظام والمتطلبات الأساسية..."

# فحص نظام التشغيل
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    print_success "نظام التشغيل: Linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    print_success "نظام التشغيل: macOS"
else
    print_error "نظام التشغيل غير مدعوم: $OSTYPE"
    exit 1
fi

# فحص Python
if check_command "python3"; then
    PYTHON_CMD="python3"
    print_success "تم العثور على Python3"
elif check_command "python"; then
    PYTHON_CMD="python"
    print_success "تم العثور على Python"
else
    print_error "لم يتم العثور على Python. يرجى تثبيت Python 3.7+"
    exit 1
fi

# فحص إصدار Python
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
print_status "إصدار Python: $PYTHON_VERSION"

# فحص pip
if check_command "pip3"; then
    PIP_CMD="pip3"
    print_success "تم العثور على pip3"
elif check_command "pip"; then
    PIP_CMD="pip"
    print_success "تم العثور على pip"
else
    print_error "لم يتم العثور على pip. يرجى تثبيت pip"
    exit 1
fi

# ===================================================================
#  الخطوة 2: تثبيت المتطلبات الأساسية
# ===================================================================

print_status "الخطوة 2/5: تثبيت المتطلبات الأساسية..."

# تحديث قائمة الحزم
print_status "تحديث قائمة الحزم..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update -y
    print_success "تم تحديث قائمة الحزم (apt-get)"
elif command -v yum &> /dev/null; then
    sudo yum update -y
    print_success "تم تحديث قائمة الحزم (yum)"
elif command -v dnf &> /dev/null; then
    sudo dnf update -y
    print_success "تم تحديث قائمة الحزم (dnf)"
else
    print_warning "لم يتم العثور على مدير حزم معروف"
fi

# تثبيت المتطلبات الأساسية
print_status "تثبيت المتطلبات الأساسية..."
if command -v apt-get &> /dev/null; then
    sudo apt-get install -y python3-pip python3-venv git curl wget
    print_success "تم تثبيت المتطلبات الأساسية (apt-get)"
elif command -v yum &> /dev/null; then
    sudo yum install -y python3-pip python3-venv git curl wget
    print_success "تم تثبيت المتطلبات الأساسية (yum)"
elif command -v dnf &> /dev/null; then
    sudo dnf install -y python3-pip python3-venv git curl wget
    print_success "تم تثبيت المتطلبات الأساسية (dnf)"
fi

# ===================================================================
#  الخطوة 3: فحص وتثبيت مكتبات Python
# ===================================================================

print_status "الخطوة 3/5: فحص وتثبيت مكتبات Python..."

# فحص وجود ملف requirements.txt
if check_file "requirements.txt"; then
    print_success "تم العثور على ملف requirements.txt"
    
    # تثبيت المكتبات
    print_status "تثبيت مكتبات Python..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # على Linux، استخدم --break-system-packages إذا لزم الأمر
        $PIP_CMD install --break-system-packages -r requirements.txt
    else
        $PIP_CMD install -r requirements.txt
    fi
    
    if [ $? -eq 0 ]; then
        print_success "تم تثبيت جميع المكتبات بنجاح"
    else
        print_warning "حدث خطأ في تثبيت بعض المكتبات. سيتم المحاولة مرة أخرى..."
        $PIP_CMD install --break-system-packages -r requirements.txt --force-reinstall
    fi
else
    print_error "لم يتم العثور على ملف requirements.txt"
    exit 1
fi

# ===================================================================
#  الخطوة 4: فحص الملفات المطلوبة
# ===================================================================

print_status "الخطوة 4/5: فحص الملفات المطلوبة..."

# فحص وجود الملفات الأساسية
REQUIRED_FILES=("khayal.py" "add.py" "config.py")
MISSING_FILES=()

for file in "${REQUIRED_FILES[@]}"; do
    if check_file "$file"; then
        print_success "تم العثور على $file"
    else
        print_error "ملف مفقود: $file"
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    print_error "الملفات المفقودة: ${MISSING_FILES[*]}"
    print_error "يرجى التأكد من وجود جميع الملفات المطلوبة"
    exit 1
fi

# فحص وجود قاعدة البيانات
if check_file "accounts.db"; then
    print_success "تم العثور على قاعدة البيانات accounts.db"
else
    print_warning "لم يتم العثور على قاعدة البيانات accounts.db"
    print_status "سيتم إنشاؤها تلقائياً عند تشغيل add.py"
fi

# ===================================================================
#  الخطوة 5: تشغيل الملفات
# ===================================================================

print_status "الخطوة 5/5: تشغيل الملفات..."

# تشغيل add.py أولاً
print_status "تشغيل add.py..."
$PYTHON_CMD add.py &
ADD_PID=$!

# انتظار قليل للتأكد من بدء add.py
sleep 3

# فحص إذا كان add.py يعمل
if ps -p $ADD_PID > /dev/null; then
    print_success "تم تشغيل add.py بنجاح (PID: $ADD_PID)"
else
    print_warning "فشل في تشغيل add.py. سيتم المتابعة..."
fi

# انتظار قليل قبل تشغيل khayal.py
sleep 2

# تشغيل khayal.py
print_status "تشغيل khayal.py..."
$PYTHON_CMD khayal.py &
KHAYAL_PID=$!

# انتظار قليل للتأكد من بدء khayal.py
sleep 5

# فحص حالة khayal.py
if ps -p $KHAYAL_PID > /dev/null; then
    print_success "تم تشغيل khayal.py بنجاح (PID: $KHAYAL_PID)"
else
    print_error "فشل في تشغيل khayal.py"
    exit 1
fi

# ===================================================================
#  عرض معلومات التشغيل
# ===================================================================

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    تم التثبيت والتشغيل بنجاح!               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

print_success "معلومات التشغيل:"
echo "  • add.py: PID $ADD_PID"
echo "  • khayal.py: PID $KHAYAL_PID"
echo "  • Python: $PYTHON_CMD ($PYTHON_VERSION)"
echo "  • pip: $PIP_CMD"

echo ""
print_status "أوامر مفيدة:"
echo "  • عرض العمليات: ps aux | grep python"
echo "  • إيقاف البوت: pkill -f khayal.py"
echo "  • إيقاف add.py: pkill -f add.py"
echo "  • عرض السجلات: tail -f detailed_reports.log"

echo ""
print_success "🎉 تم تشغيل البوت بنجاح! يمكنك الآن استخدامه على تيليجرام."

# حفظ PIDs في ملف للاستخدام لاحقاً
echo "$ADD_PID" > .add_pid
echo "$KHAYAL_PID" > .khayal_pid

print_status "تم حفظ PIDs في ملفات .add_pid و .khayal_pid"