// static/js/main.js

// 全局配置
const CONFIG = {
    apiBaseUrl: '/api',
    maxFileSize: 100 * 1024 * 1024, // 100MB
    allowedFileTypes: ['.csv', '.xlsx', '.xls'],
    theme: localStorage.getItem('theme') || 'light'
};

// 初始化函数
function initializeApp() {
    // 设置主题
    document.body.setAttribute('data-theme', CONFIG.theme);

    // 初始化工具提示
    initTooltips();

    // 初始化弹出框
    initPopovers();

    // 设置Ajax请求头
    setupAjaxHeaders();

    // 绑定全局事件
    bindGlobalEvents();

    console.log('LG-DBM系统初始化完成');
}

// 初始化工具提示
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// 初始化弹出框
function initPopovers() {
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
}

// 设置Ajax请求头
function setupAjaxHeaders() {
    if (typeof $ !== 'undefined') {
        $.ajaxSetup({
            headers: {
                'X-CSRFToken': getCookie('csrf_token')
            }
        });
    }
}

// 获取Cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// 绑定全局事件
function bindGlobalEvents() {
    // 页面加载完成
    window.addEventListener('load', function() {
        document.body.classList.add('loaded');

        const loading = document.getElementById('loading');
        if (loading) {
            loading.style.display = 'none';
        }
    });

    // 阻止表单重复提交
    document.addEventListener('submit', function(e) {
        const form = e.target;
        if (form.tagName === 'FORM') {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                const originalText = submitBtn.innerHTML;
                submitBtn.dataset.originalText = originalText;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>处理中...';

                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = submitBtn.dataset.originalText || '提交';
                }, 5000);
            }
        }
    });

    // 全局错误处理
    window.addEventListener('error', function(e) {
        console.error('全局错误:', e.error);
        showToast('发生错误，请刷新页面重试', 'error');
    });

    // 页面可见性变化
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            console.log('页面重新可见');
        }
    });
}

// 显示Toast通知
function showToast(message, type = 'info', duration = 5000) {
    const toastContainer = document.getElementById('toast-container') || createToastContainer();

    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `toast align-items-center border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    const bgColor = type === 'success' ? 'var(--secondary)' :
                    type === 'error' ? 'var(--danger)' :
                    type === 'warning' ? 'var(--warning)' : 'var(--primary)';

    toast.style.background = `linear-gradient(135deg, ${bgColor}, ${bgColor}dd)`;
    toast.style.color = 'white';
    toast.style.borderRadius = '8px';

    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'} me-2"></i>
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;

    toastContainer.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast, {
        delay: duration
    });

    bsToast.show();

    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });

    return bsToast;
}

// 创建Toast容器
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '1060';
    document.body.appendChild(container);
    return container;
}

// 显示确认对话框
function showConfirm(message, callback, options = {}) {
    const title = options.title || '确认操作';
    const confirmText = options.confirmText || '确认';
    const cancelText = options.cancelText || '取消';
    const type = options.type || 'warning';

    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-exclamation-triangle me-2 text-${type}"></i>${title}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p>${message}</p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">${cancelText}</button>
                    <button type="button" class="btn btn-${type}" id="confirmBtn">${confirmText}</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();

    modal.querySelector('#confirmBtn').addEventListener('click', function() {
        if (typeof callback === 'function') {
            callback();
        }
        modalInstance.hide();
    });

    modal.addEventListener('hidden.bs.modal', function() {
        document.body.removeChild(modal);
    });
}

// 加载数据
function loadData(url, params = {}, options = {}) {
    const method = options.method || 'GET';
    const showLoading = options.showLoading !== false;

    let loadingToast;
    if (showLoading) {
        loadingToast = showToast('加载中...', 'info', 0);
    }

    const fetchOptions = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (method !== 'GET' && method !== 'HEAD') {
        fetchOptions.body = JSON.stringify(params);
    } else if (Object.keys(params).length > 0) {
        url += '?' + new URLSearchParams(params).toString();
    }

    return fetch(url, fetchOptions)
        .then(response => {
            if (loadingToast) {
                loadingToast.hide();
            }

            if (!response.ok) {
                throw new Error(`HTTP错误 ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return response.json();
            } else {
                return response.text();
            }
        })
        .then(data => {
            if (options.success) {
                options.success(data);
            }
            return data;
        })
        .catch(error => {
            if (loadingToast) {
                loadingToast.hide();
            }

            console.error('加载数据失败:', error);

            if (options.error) {
                options.error(error);
            } else {
                showToast(`加载失败: ${error.message}`, 'error');
            }

            throw error;
        });
}

// 导出数据
function exportData(url, params = {}, filename = 'export.xlsx') {
    const queryString = new URLSearchParams(params).toString();
    const exportUrl = queryString ? `${url}?${queryString}` : url;

    const a = document.createElement('a');
    a.href = exportUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    showToast('开始下载文件', 'success');
}

// 格式化数字
function formatNumber(num, decimals = 2) {
    if (isNaN(num)) return '0';

    const fixed = parseFloat(num).toFixed(decimals);
    const parts = fixed.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.join('.');
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';

    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 格式化日期
function formatDate(date, format = 'YYYY-MM-DD HH:mm:ss') {
    if (!date) return '';

    const d = new Date(date);
    const pad = (n) => n.toString().padStart(2, '0');

    const replacements = {
        'YYYY': d.getFullYear(),
        'MM': pad(d.getMonth() + 1),
        'DD': pad(d.getDate()),
        'HH': pad(d.getHours()),
        'mm': pad(d.getMinutes()),
        'ss': pad(d.getSeconds())
    };

    return format.replace(/YYYY|MM|DD|HH|mm|ss/g, match => replacements[match]);
}

// 深度复制对象
function deepCopy(obj) {
    if (obj === null || typeof obj !== 'object') {
        return obj;
    }

    if (obj instanceof Date) {
        return new Date(obj.getTime());
    }

    if (obj instanceof Array) {
        return obj.reduce((arr, item, i) => {
            arr[i] = deepCopy(item);
            return arr;
        }, []);
    }

    if (typeof obj === 'object') {
        return Object.keys(obj).reduce((newObj, key) => {
            newObj[key] = deepCopy(obj[key]);
            return newObj;
        }, {});
    }
}

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 节流函数
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// 验证邮箱格式
function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

// 验证手机号格式
function isValidPhone(phone) {
    const re = /^1[3-9]\d{9}$/;
    return re.test(phone);
}

// 获取URL参数
function getUrlParam(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

// 设置URL参数
function setUrlParam(name, value) {
    const url = new URL(window.location);
    url.searchParams.set(name, value);
    window.history.pushState({}, '', url);
}

// 移除URL参数
function removeUrlParam(name) {
    const url = new URL(window.location);
    url.searchParams.delete(name);
    window.history.pushState({}, '', url);
}

// 检查元素是否在视口中
function isInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}

// 滚动到元素
function scrollToElement(element, offset = 0) {
    const elementPosition = element.getBoundingClientRect().top + window.pageYOffset;
    const offsetPosition = elementPosition - offset;

    window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
    });
}

// 复制到剪贴板
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    } else {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();

        return new Promise((resolve, reject) => {
            document.execCommand('copy') ? resolve() : reject();
            textArea.remove();
        });
    }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', initializeApp);

// 全局导出
window.AppUtils = {
    showToast,
    showConfirm,
    loadData,
    exportData,
    formatNumber,
    formatFileSize,
    formatDate,
    deepCopy,
    debounce,
    throttle,
    isValidEmail,
    isValidPhone,
    getUrlParam,
    setUrlParam,
    removeUrlParam,
    isInViewport,
    scrollToElement,
    copyToClipboard
};