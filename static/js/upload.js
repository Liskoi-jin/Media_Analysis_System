// static/js/upload.js

// 文件上传相关功能

class FileUploader {
    constructor(options = {}) {
        this.options = {
            dropZone: '#dropZone',
            fileInput: '#fileInput',
            fileList: '#fileList',
            maxFiles: 10,
            maxSize: 100 * 1024 * 1024, // 100MB
            allowedTypes: ['.csv', '.xlsx', '.xls'],
            ...options
        };

        this.files = [];
        this.initialize();
    }

    initialize() {
        this.dropZone = document.querySelector(this.options.dropZone);
        this.fileInput = document.querySelector(this.options.fileInput);
        this.fileList = document.querySelector(this.options.fileList);
        this.selectedFiles = document.querySelector(this.options.fileList + ' #selectedFiles');

        if (!this.selectedFiles) {
            this.selectedFiles = document.createElement('div');
            this.selectedFiles.id = 'selectedFiles';
            this.selectedFiles.className = 'list-group';
            this.fileList.appendChild(this.selectedFiles);
        }

        this.bindEvents();
    }

    bindEvents() {
        // 点击上传区域
        if (this.dropZone) {
            this.dropZone.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT') {
                    this.fileInput.click();
                }
            });

            // 拖放事件
            this.dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                this.dropZone.classList.add('drag-over');
            });

            this.dropZone.addEventListener('dragleave', () => {
                this.dropZone.classList.remove('drag-over');
            });

            this.dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                this.dropZone.classList.remove('drag-over');

                const files = Array.from(e.dataTransfer.files);
                this.processFiles(files);
            });
        }

        // 文件输入变化
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => {
                const files = Array.from(e.target.files);
                this.processFiles(files);
            });
        }
    }

    processFiles(files) {
        const validFiles = [];
        const errors = [];

        files.forEach(file => {
            // 检查文件数量
            if (this.files.length + validFiles.length >= this.options.maxFiles) {
                errors.push(`最多只能上传 ${this.options.maxFiles} 个文件`);
                return;
            }

            // 检查文件类型
            const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
            if (!this.options.allowedTypes.includes(fileExtension)) {
                errors.push(`文件 "${file.name}" 类型不支持，支持的类型: ${this.options.allowedTypes.join(', ')}`);
                return;
            }

            // 检查文件大小
            if (file.size > this.options.maxSize) {
                errors.push(`文件 "${file.name}" 大小超过限制 (${this.formatFileSize(this.options.maxSize)})`);
                return;
            }

            validFiles.push(file);
        });

        // 显示错误信息
        if (errors.length > 0) {
            this.showErrors(errors);
        }

        // 添加有效文件
        if (validFiles.length > 0) {
            this.addFiles(validFiles);
        }
    }

    addFiles(files) {
        files.forEach(file => {
            // 检查是否已存在同名文件
            if (this.files.some(f => f.name === file.name && f.size === file.size)) {
                return;
            }

            // 添加到文件列表
            this.files.push(file);
            this.addFileToList(file);
        });

        this.updateUI();
    }

    addFileToList(file) {
        const fileItem = document.createElement('div');
        fileItem.className = 'list-group-item d-flex justify-content-between align-items-center';
        fileItem.dataset.filename = file.name;

        const fileInfo = document.createElement('div');
        fileInfo.className = 'd-flex align-items-center';

        const fileIcon = document.createElement('i');
        fileIcon.className = this.getFileIcon(file.name);
        fileIcon.style.marginRight = '10px';

        const fileName = document.createElement('span');
        fileName.textContent = file.name;
        fileName.style.fontWeight = '500';

        const fileSize = document.createElement('small');
        fileSize.className = 'text-muted';
        fileSize.textContent = ` (${this.formatFileSize(file.size)})`;

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn btn-sm btn-outline-danger';
        removeBtn.innerHTML = '<i class="fas fa-times"></i>';
        removeBtn.addEventListener('click', () => {
            this.removeFile(file.name);
        });

        fileName.appendChild(fileSize);
        fileInfo.appendChild(fileIcon);
        fileInfo.appendChild(fileName);

        fileItem.appendChild(fileInfo);
        fileItem.appendChild(removeBtn);

        this.selectedFiles.appendChild(fileItem);
    }

    removeFile(filename) {
        this.files = this.files.filter(file => file.name !== filename);

        // 从UI中移除
        const fileItem = this.selectedFiles.querySelector(`[data-filename="${filename}"]`);
        if (fileItem) {
            fileItem.remove();
        }

        this.updateUI();
    }

    removeAllFiles() {
        this.files = [];
        this.selectedFiles.innerHTML = '';
        this.updateUI();
    }

    updateUI() {
        // 显示/隐藏文件列表
        if (this.files.length > 0) {
            this.fileList.style.display = 'block';

            // 更新提交按钮状态
            const submitBtn = document.querySelector('#submitBtn');
            if (submitBtn) {
                submitBtn.disabled = false;
            }

            // 更新文件计数
            const fileCount = document.querySelector('#fileCount');
            if (fileCount) {
                fileCount.textContent = `已选择 ${this.files.length} 个文件`;
            }
        } else {
            this.fileList.style.display = 'none';

            const submitBtn = document.querySelector('#submitBtn');
            if (submitBtn) {
                submitBtn.disabled = true;
            }
        }
    }

    getFileIcon(filename) {
        const extension = filename.split('.').pop().toLowerCase();

        switch (extension) {
            case 'csv':
                return 'fas fa-file-csv text-success';
            case 'xlsx':
            case 'xls':
                return 'fas fa-file-excel text-success';
            case 'pdf':
                return 'fas fa-file-pdf text-danger';
            case 'doc':
            case 'docx':
                return 'fas fa-file-word text-primary';
            default:
                return 'fas fa-file text-secondary';
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';

        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    showErrors(errors) {
        const errorList = errors.map(error => `<li>${error}</li>`).join('');
        const errorHtml = `
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <h6><i class="fas fa-exclamation-triangle me-2"></i>上传错误</h6>
                <ul class="mb-0">
                    ${errorList}
                </ul>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        // 插入到上传区域前面
        if (this.dropZone) {
            this.dropZone.insertAdjacentHTML('beforebegin', errorHtml);
        }
    }

    getFormData() {
        const formData = new FormData();

        this.files.forEach(file => {
            formData.append('files', file);
        });

        return formData;
    }

    getFiles() {
        return this.files;
    }

    getFileCount() {
        return this.files.length;
    }

    reset() {
        this.removeAllFiles();
        if (this.fileInput) {
            this.fileInput.value = '';
        }
    }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', function() {
    // 初始化文件上传器
    const uploader = new FileUploader({
        dropZone: '#dropZone',
        fileInput: '#fileInput',
        fileList: '#fileList',
        maxFiles: 20,
        maxSize: 200 * 1024 * 1024 // 200MB
    });

    // 将上传器暴露给全局
    window.fileUploader = uploader;

    // 表单提交处理
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const files = uploader.getFiles();
            if (files.length === 0) {
                if (window.AppUtils) {
                    window.AppUtils.showToast('请先选择要上传的文件', 'warning');
                } else {
                    alert('请先选择要上传的文件');
                }
                return;
            }

            // 获取表单数据
            const formData = uploader.getFormData();

            // 添加其他表单字段
            const analysisMode = document.querySelector('input[name="analysisMode"]:checked')?.value || 'media';
            const category = document.getElementById('dataCategory')?.value || '默认类目';

            formData.append('analysis_mode', analysisMode);
            formData.append('category', category);

            // 如果是自定义模式，添加额外配置
            if (analysisMode === 'custom') {
                const customConfig = {
                    includeWorkload: document.getElementById('customWorkload')?.checked || false,
                    includeQuality: document.getElementById('customQuality')?.checked || false,
                    includeCost: document.getElementById('customCost')?.checked || false,
                    topN: document.getElementById('topN')?.value || 10,
                    useOriginalState: document.getElementById('useOriginalState')?.checked || false
                };
                formData.append('custom_config', JSON.stringify(customConfig));
            }

            // 显示上传进度
            const progressHtml = `
                <div class="card mt-3">
                    <div class="card-body">
                        <h6><i class="fas fa-upload me-2"></i>上传进度</h6>
                        <div class="progress" style="height: 10px;">
                            <div class="progress-bar progress-bar-striped progress-bar-animated"
                                 role="progressbar" style="width: 0%"></div>
                        </div>
                        <div class="text-center mt-2">
                            <span class="upload-status">准备上传...</span>
                        </div>
                    </div>
                </div>
            `;

            uploadForm.insertAdjacentHTML('afterend', progressHtml);
            const progressBar = document.querySelector('.progress-bar');
            const uploadStatus = document.querySelector('.upload-status');

            // 禁用提交按钮
            const submitBtn = uploadForm.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>上传中...';

            // 发送上传请求
            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percentComplete = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percentComplete + '%';
                    uploadStatus.textContent = `上传中: ${percentComplete}%`;
                }
            });

            xhr.addEventListener('load', function() {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);

                        if (response.success) {
                            progressBar.classList.remove('progress-bar-animated');
                            progressBar.classList.remove('progress-bar-striped');
                            progressBar.classList.add('bg-success');
                            uploadStatus.innerHTML = `<i class="fas fa-check-circle text-success me-1"></i>上传成功！正在分析数据...`;

                            setTimeout(() => {
                                window.location.href = response.redirect_url || '/dashboard';
                            }, 1500);
                        } else {
                            progressBar.classList.add('bg-danger');
                            uploadStatus.innerHTML = `<i class="fas fa-times-circle text-danger me-1"></i>上传失败: ${response.message}`;
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalBtnText;
                        }
                    } catch (error) {
                        progressBar.classList.add('bg-danger');
                        uploadStatus.innerHTML = `<i class="fas fa-times-circle text-danger me-1"></i>上传失败: 响应解析错误`;
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalBtnText;
                    }
                } else {
                    progressBar.classList.add('bg-danger');
                    uploadStatus.innerHTML = `<i class="fas fa-times-circle text-danger me-1"></i>上传失败: 服务器错误 (${xhr.status})`;
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalBtnText;
                }
            });

            xhr.addEventListener('error', function() {
                progressBar.classList.add('bg-danger');
                uploadStatus.innerHTML = `<i class="fas fa-times-circle text-danger me-1"></i>上传失败: 网络错误`;
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            });

            xhr.open('POST', uploadForm.action);
            xhr.send(formData);
        });
    }

    // 重置按钮
    const resetBtn = uploadForm?.querySelector('button[type="reset"]');
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            uploader.reset();

            // 重置分析模式选择
            const modeMedia = document.getElementById('modeMedia');
            if (modeMedia) {
                modeMedia.checked = true;
            }

            const customConfig = document.getElementById('customConfig');
            if (customConfig) {
                customConfig.style.display = 'none';
            }

            // 重置数据类别
            const dataCategory = document.getElementById('dataCategory');
            if (dataCategory) {
                dataCategory.value = 'all';
            }

            if (window.AppUtils) {
                window.AppUtils.showToast('表单已重置', 'info');
            }
        });
    }

    // 文件拖放效果
    document.addEventListener('dragover', function(e) {
        e.preventDefault();
    });

    document.addEventListener('drop', function(e) {
        e.preventDefault();
    });
});