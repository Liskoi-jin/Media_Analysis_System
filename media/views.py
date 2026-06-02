# media/views.py
"""
媒介管理视图函数
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from models import db, MediaPersonnel
from auth.utils import admin_required, login_required
from datetime import datetime
import logging
import csv
import io
import chardet

# 修改这里：从 analyzers.utils 导入，而不是 analyzers.utils
from analyzers.utils import (
    logger, ID_TO_NAME_MAPPING, FLOWER_TO_NAME_MAPPING, NAME_TO_GROUP_MAPPING,
    load_mappings_from_db
)

media_bp = Blueprint('media', __name__, url_prefix='/media')


@media_bp.route('/list')
@login_required
def media_list():
    """媒介列表页 - 支持分页"""
    # 获取查询参数
    keyword = request.args.get('keyword', '').strip()
    group = request.args.get('group', '').strip()
    status = request.args.get('status', '').strip()

    # 分页参数 - 默认每页15条
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)  # 默认每页15条
    valid_per_page = [10, 15, 20, 30, 50, 100]  # 增加15和30选项
    if per_page not in valid_per_page:
        per_page = 15

    # 构建查询
    query = MediaPersonnel.query.filter_by(deleted=False)

    if keyword:
        query = query.filter(
            db.or_(
                MediaPersonnel.user_name.like(f'%{keyword}%'),
                MediaPersonnel.nike_name.like(f'%{keyword}%'),
                MediaPersonnel.flower_name.like(f'%{keyword}%'),
                MediaPersonnel.dept_name.like(f'%{keyword}%')
            )
        )

    if group and group != '全部' and group != '':
        # 直接使用部门名称进行筛选
        query = query.filter(MediaPersonnel.dept_name == group)

    if status == 'enabled':
        query = query.filter_by(state=1)
    elif status == 'disabled':
        query = query.filter_by(state=0)

    # 分页查询
    pagination = query.order_by(MediaPersonnel.create_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    medias = pagination.items

    # 获取所有可用的部门名称（用于筛选）
    all_depts = db.session.query(MediaPersonnel.dept_name).filter(
        MediaPersonnel.deleted == False,
        MediaPersonnel.dept_name.isnot(None),
        MediaPersonnel.dept_name != ''
    ).distinct().order_by(MediaPersonnel.dept_name).all()

    groups = ['全部']
    for dept in all_depts:
        if dept[0] and dept[0] not in groups:
            groups.append(dept[0])

    return render_template('media/media_list.html',
                           medias=medias,
                           groups=groups,
                           current_group=group,
                           keyword=keyword,
                           status=status,
                           pagination=pagination,
                           per_page=per_page,
                           page=page)


@media_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def media_add():
    """新增媒介"""
    if request.method == 'POST':
        try:
            user_id = request.form.get('user_id', '').strip()
            user_name = request.form.get('user_name', '').strip()
            nike_name = request.form.get('nike_name', '').strip()
            flower_name = request.form.get('flower_name', '').strip()
            dept_name = request.form.get('dept_name', '').strip()
            parent_dept_name = request.form.get('parent_dept_name', '').strip()
            post_name = request.form.get('post_name', '').strip()
            media_tag = request.form.get('media_tag', '').strip()
            state = 1 if request.form.get('state') == 'on' else 0

            if not user_id or not user_name:
                flash('用户ID和用户名不能为空', 'danger')
                return render_template('media/media_add.html', form=request.form)

            existing = MediaPersonnel.query.filter_by(user_id=user_id, deleted=False).first()
            if existing:
                flash(f'用户ID {user_id} 已存在', 'danger')
                return render_template('media/media_add.html', form=request.form)

            media = MediaPersonnel(
                user_id=int(user_id),
                user_name=user_name,
                nike_name=nike_name,
                flower_name=flower_name,
                dept_name=dept_name,
                parent_dept_name=parent_dept_name,
                post_name=post_name,
                media_tag=media_tag,
                state=state,
                creator='admin',
                create_time=datetime.now(),
                deleted=False,
                tenant_id=1
            )

            db.session.add(media)
            db.session.commit()
            flash('✅ 媒介添加成功', 'success')
            return redirect(url_for('media.media_list'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"添加媒介失败: {e}")
            flash(f'❌ 添加失败：{str(e)}', 'danger')
            return render_template('media/media_add.html', form=request.form)

    return render_template('media/media_add.html')


@media_bp.route('/edit/<int:media_id>', methods=['GET', 'POST'])
@admin_required
def media_edit(media_id):
    """编辑媒介"""
    media = MediaPersonnel.query.get_or_404(media_id)

    if request.method == 'POST':
        try:
            media.user_id = int(request.form.get('user_id', media.user_id))
            media.user_name = request.form.get('user_name', media.user_name).strip()
            media.nike_name = request.form.get('nike_name', media.nike_name).strip()
            media.flower_name = request.form.get('flower_name', media.flower_name).strip()
            media.dept_name = request.form.get('dept_name', media.dept_name).strip()
            media.parent_dept_name = request.form.get('parent_dept_name', media.parent_dept_name).strip()
            media.post_name = request.form.get('post_name', media.post_name).strip()
            media.media_tag = request.form.get('media_tag', media.media_tag).strip()
            media.state = 1 if request.form.get('state') == 'on' else 0
            media.updater = 'admin'
            media.update_time = datetime.now()

            db.session.commit()
            flash('✅ 媒介更新成功', 'success')
            return redirect(url_for('media.media_list'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"更新媒介失败: {e}")
            flash(f'❌ 更新失败：{str(e)}', 'danger')
            return render_template('media/media_edit.html', media=media)

    return render_template('media/media_edit.html', media=media)


@media_bp.route('/delete/<int:media_id>', methods=['POST'])
@admin_required
def media_delete(media_id):
    """软删除媒介"""
    try:
        media = MediaPersonnel.query.get_or_404(media_id)
        media.deleted = True
        media.updater = 'admin'
        media.update_time = datetime.now()
        db.session.commit()
        flash('✅ 媒介已删除', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除媒介失败: {e}")
        flash(f'❌ 删除失败：{str(e)}', 'danger')

    return redirect(url_for('media.media_list'))


@media_bp.route('/init', methods=['POST'])
@admin_required
def init_default_groups():
    """初始化默认小组（从utils.py导入）"""
    try:
        from analyzers.utils import _ID_TO_NAME_MAPPING, _FLOWER_TO_NAME_MAPPING, _NAME_TO_GROUP_MAPPING

        added_count = 0
        updated_count = 0

        for user_id, real_name in _ID_TO_NAME_MAPPING.items():
            group = _NAME_TO_GROUP_MAPPING.get(real_name, '其他组')
            flower = None
            for f, n in _FLOWER_TO_NAME_MAPPING.items():
                if n == real_name:
                    flower = f
                    break

            existing = MediaPersonnel.query.filter_by(user_id=user_id, deleted=False).first()
            if existing:
                existing.nike_name = real_name
                existing.flower_name = flower
                existing.dept_name = group
                existing.updater = 'admin'
                existing.update_time = datetime.now()
                updated_count += 1
            else:
                media = MediaPersonnel(
                    user_id=user_id,
                    user_name=real_name,
                    nike_name=real_name,
                    flower_name=flower,
                    dept_name=group,
                    post_name='媒介',
                    state=1,
                    creator='admin',
                    create_time=datetime.now(),
                    deleted=False,
                    tenant_id=1
                )
                db.session.add(media)
                added_count += 1

        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'初始化完成：新增 {added_count} 条，更新 {updated_count} 条'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"初始化默认小组失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@media_bp.route('/api/mapping')
def get_mapping():
    """API接口：获取媒介映射表"""
    try:
        medias = MediaPersonnel.query.filter_by(deleted=False, state=1).all()

        id_to_name = {}
        flower_to_name = {}
        name_to_group = {}

        for media in medias:
            real_name = media.get_real_name()
            flower = media.get_flower_name()
            group = media.get_group_name()

            if media.user_id:
                id_to_name[str(media.user_id)] = real_name
            if flower:
                flower_to_name[flower] = real_name
            if real_name:
                name_to_group[real_name] = group

        return jsonify({
            'success': True,
            'data': {
                'ID_TO_NAME_MAPPING': id_to_name,
                'FLOWER_TO_NAME_MAPPING': flower_to_name,
                'NAME_TO_GROUP_MAPPING': name_to_group
            }
        })

    except Exception as e:
        logger.error(f"获取映射表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@media_bp.route('/api/refresh-mapping', methods=['POST'])
@admin_required
def refresh_mapping():
    """API接口：刷新媒介映射表 - 从数据库重新加载"""
    try:
        from flask import current_app

        # 重新加载映射表
        success = load_mappings_from_db(current_app)

        if success:
            from analyzers.utils import ID_TO_NAME_MAPPING, FLOWER_TO_NAME_MAPPING, NAME_TO_GROUP_MAPPING

            return jsonify({
                'success': True,
                'message': '映射表刷新成功',
                'count': {
                    'id_mapping': len(ID_TO_NAME_MAPPING),
                    'flower_mapping': len(FLOWER_TO_NAME_MAPPING),
                    'group_mapping': len(NAME_TO_GROUP_MAPPING)
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': '映射表加载失败，请检查数据库连接'
            }), 500

    except Exception as e:
        logger.error(f"刷新映射表失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'刷新失败: {str(e)}'
        }), 500


@media_bp.route('/import', methods=['GET', 'POST'])
@admin_required
def media_import():
    """导入媒介数据CSV文件"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('❌ 请选择要上传的文件', 'danger')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('❌ 未选择文件', 'danger')
            return redirect(request.url)

        if not file.filename.endswith('.csv'):
            flash('❌ 请上传CSV格式文件', 'danger')
            return redirect(request.url)

        try:
            # 读取文件内容
            file_content = file.read()

            # 方法1：使用 chardet 检测编码
            detected = chardet.detect(file_content)
            detected_encoding = detected.get('encoding', 'utf-8')
            logger.info(f"chardet检测到的编码: {detected_encoding}, 置信度: {detected.get('confidence', 0)}")

            # 方法2：尝试多种编码（优先级：utf-8-sig > utf-8 > gbk > gb18030 > gb2312 > latin-1）
            encodings_to_try = ['utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'gb2312', 'latin-1']

            # 将检测到的编码放在优先位置（但避免重复）
            if detected_encoding and detected_encoding.lower() in encodings_to_try:
                encodings_to_try.remove(detected_encoding.lower())
                encodings_to_try.insert(0, detected_encoding.lower())

            content = None
            used_encoding = None

            for enc in encodings_to_try:
                try:
                    content = file_content.decode(enc)
                    used_encoding = enc
                    logger.info(f"✅ 成功使用 {enc} 编码解析文件")
                    break
                except (UnicodeDecodeError, LookupError) as e:
                    logger.debug(f"编码 {enc} 解码失败: {e}")
                    continue

            if content is None:
                raise Exception("无法解析文件编码，请确保文件是UTF-8或GBK格式")

            # 处理 BOM 头
            if content.startswith('\ufeff'):
                content = content[1:]
                logger.info("已移除 UTF-8 BOM 头")

            logger.info(f"最终使用编码: {used_encoding}")

            # 使用csv模块解析
            csv_reader = csv.DictReader(io.StringIO(content))

            # 获取CSV的字段名
            fieldnames = csv_reader.fieldnames
            logger.info(f"CSV字段: {fieldnames}")

            # 统计
            success_count = 0
            error_count = 0
            update_count = 0

            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    # 处理布尔值字段
                    deleted = False
                    if 'deleted' in row and row['deleted']:
                        deleted = row['deleted'].lower() in ['true', '1', 'yes']

                    state = 1
                    if 'state' in row and row['state']:
                        state = 1 if str(row['state']).lower() in ['true', '1', 'yes', '启用', '1'] else 0

                    # 处理时间字段
                    create_time = None
                    if 'create_time' in row and row['create_time']:
                        try:
                            # 尝试解析ISO格式时间
                            create_time = datetime.fromisoformat(row['create_time'].replace('Z', '+00:00'))
                        except:
                            create_time = datetime.now()

                    # 处理数值字段
                    def safe_float(value, default=0.0):
                        if not value or value == '':
                            return default
                        try:
                            return float(value)
                        except:
                            return default

                    def safe_int(value, default=0):
                        if not value or value == '':
                            return default
                        try:
                            return int(float(value))
                        except:
                            return default

                    # 检查是否已存在
                    user_id = safe_int(row.get('user_id', 0))
                    if user_id == 0:
                        logger.warning(f"第{row_num}行: 跳过无效user_id的行: {row}")
                        error_count += 1
                        continue

                    existing = MediaPersonnel.query.filter_by(user_id=user_id, deleted=False).first()

                    if existing:
                        # 更新现有记录
                        if row.get('nike_name'):
                            existing.nike_name = row['nike_name']
                        if row.get('flower_name'):
                            existing.flower_name = row['flower_name']
                        if row.get('media_tag'):
                            existing.media_tag = row['media_tag']
                        if row.get('dept_name'):
                            existing.dept_name = row['dept_name']
                        if row.get('parent_dept_name'):
                            existing.parent_dept_name = row['parent_dept_name']
                        if row.get('post_name'):
                            existing.post_name = row['post_name']
                        if row.get('user_name'):
                            existing.user_name = row['user_name']
                        existing.state = state
                        existing.updater = 'admin'
                        existing.update_time = datetime.now()
                        update_count += 1
                    else:
                        # 创建新记录
                        media = MediaPersonnel(
                            user_id=user_id,
                            user_name=row.get('user_name', ''),
                            nike_name=row.get('nike_name', ''),
                            flower_name=row.get('flower_name', ''),
                            media_tag=row.get('media_tag', ''),
                            dept_name=row.get('dept_name', ''),
                            parent_dept_name=row.get('parent_dept_name', ''),
                            post_name=row.get('post_name', ''),
                            state=state,
                            creator='admin',
                            create_time=create_time or datetime.now(),
                            deleted=deleted,
                            tenant_id=safe_int(row.get('tenant_id', 1)),
                            linked_influencer_count=safe_int(row.get('linked_influencer_count', 0)),
                            total_bd=safe_int(row.get('total_bd', 0)),
                            total_submissions=safe_int(row.get('total_submissions', 0)),
                            total_scheduled=safe_int(row.get('total_scheduled', 0)),
                            avg_cpm=safe_float(row.get('avg_cpm', 0)),
                            avg_cpe=safe_float(row.get('avg_cpe', 0)),
                            avg_cost=safe_float(row.get('avg_cost', 0)),
                            valid_submission_rate=safe_float(row.get('valid_submission_rate', 0)),
                            valid_scheduled_rate=safe_float(row.get('valid_scheduled_rate', 0)),
                            timely_fill_rate=safe_float(row.get('timely_fill_rate', 0)),
                            ad_selection_rate=safe_float(row.get('ad_selection_rate', 0)),
                            interaction_rate_per_hundred=safe_float(row.get('interaction_rate_per_hundred', 0)),
                            interaction_rate_per_thousand=safe_float(row.get('interaction_rate_per_thousand', 0))
                        )
                        db.session.add(media)
                        success_count += 1

                    # 每100条提交一次
                    if (success_count + update_count) % 100 == 0:
                        db.session.commit()
                        logger.info(f"已处理 {success_count + update_count} 条记录")

                except Exception as e:
                    logger.error(f"第{row_num}行处理失败: {e}, 行内容: {row}")
                    error_count += 1
                    continue

            # 最终提交
            db.session.commit()

            # 刷新映射表
            from flask import current_app
            load_mappings_from_db(current_app)

            flash(f'✅ 导入完成！新增 {success_count} 条，更新 {update_count} 条，失败 {error_count} 条', 'success')

        except Exception as e:
            db.session.rollback()
            logger.error(f"导入失败: {e}", exc_info=True)
            flash(f'❌ 导入失败: {str(e)}', 'danger')

        return redirect(url_for('media.media_list'))

    return render_template('media/media_import.html')


@media_bp.route('/api/toggle-status/<int:media_id>', methods=['POST'])
@admin_required
def toggle_media_status(media_id):
    """API：切换媒介启用/禁用状态"""
    try:
        media = MediaPersonnel.query.get_or_404(media_id)
        data = request.get_json()

        if data is None or 'state' not in data:
            return jsonify({'success': False, 'error': '缺少state参数'}), 400

        new_state = 1 if data['state'] else 0

        # 更新状态
        media.state = new_state
        media.updater = 'admin'
        media.update_time = datetime.now()

        db.session.commit()

        # 刷新映射表
        from flask import current_app
        load_mappings_from_db(current_app)

        return jsonify({
            'success': True,
            'media_id': media_id,
            'state': media.state,
            'message': f'状态已切换为{"启用" if media.state == 1 else "禁用"}'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"切换状态失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@media_bp.route('/export')
@admin_required
def media_export():
    """导出媒介数据为CSV"""
    try:
        # 查询所有未删除的媒介
        medias = MediaPersonnel.query.filter_by(deleted=False).all()

        # 创建CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow([
            'id', 'user_id', 'user_name', 'wechat_user_id', 'nike_name', 'flower_name',
            'media_tag', 'dept_id', 'parent_dept_id', 'dept_name', 'parent_dept_name',
            'post_id', 'post_name', 'state', 'creator', 'create_time', 'updater',
            'update_time', 'deleted', 'tenant_id', 'linked_influencer_count',
            'total_bd', 'total_submissions', 'total_scheduled', 'avg_cpm', 'avg_cpe',
            'avg_cost', 'valid_submission_rate', 'valid_scheduled_rate',
            'timely_fill_rate', 'ad_selection_rate', 'interaction_rate_per_hundred',
            'interaction_rate_per_thousand'
        ])

        # 写入数据
        for m in medias:
            writer.writerow([
                m.id, m.user_id, m.user_name, m.wechat_user_id or '', m.nike_name or '', m.flower_name or '',
                                              m.media_tag or '', m.dept_id or '', m.parent_dept_id or '',
                                              m.dept_name or '', m.parent_dept_name or '',
                                              m.post_id or '', m.post_name or '', m.state, m.creator or '',
                m.create_time.isoformat() if m.create_time else '',
                                              m.updater or '', m.update_time.isoformat() if m.update_time else '',
                str(m.deleted).lower(), m.tenant_id, m.linked_influencer_count or 0,
                                              m.total_bd or 0, m.total_submissions or 0, m.total_scheduled or 0,
                float(m.avg_cpm) if m.avg_cpm else 0,
                float(m.avg_cpe) if m.avg_cpe else 0,
                float(m.avg_cost) if m.avg_cost else 0,
                float(m.valid_submission_rate) if m.valid_submission_rate else 0,
                float(m.valid_scheduled_rate) if m.valid_scheduled_rate else 0,
                float(m.timely_fill_rate) if m.timely_fill_rate else 0,
                float(m.ad_selection_rate) if m.ad_selection_rate else 0,
                float(m.interaction_rate_per_hundred) if m.interaction_rate_per_hundred else 0,
                float(m.interaction_rate_per_thousand) if m.interaction_rate_per_thousand else 0
            ])

        # 创建响应
        response = make_response(output.getvalue())
        response.headers[
            'Content-Disposition'] = f'attachment; filename=media_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'

        return response

    except Exception as e:
        logger.error(f"导出失败: {e}", exc_info=True)
        flash(f'❌ 导出失败: {str(e)}', 'danger')
        return redirect(url_for('media.media_list'))