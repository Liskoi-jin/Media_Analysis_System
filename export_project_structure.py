import os


def generate_tree(directory, prefix="", ignore_list=None):
    """
    递归生成目录树结构
    """
    if ignore_list is None:
        ignore_list = ['.git', '__pycache__', '.pytest_cache', '.idea', 'venv', 'env', 'node_modules', '.DS_Store']

    files = []
    dirs = []

    # 获取目录内容，并排除忽略项
    for item in sorted(os.listdir(directory)):
        if item in ignore_list:
            continue
        item_path = os.path.join(directory, item)
        if os.path.isdir(item_path):
            dirs.append(item)
        else:
            files.append(item)

    # 目录结构字符串
    tree_str = ""

    # 处理目录
    for i, dir_name in enumerate(dirs):
        is_last_dir = (i == len(dirs) - 1 and len(files) == 0)
        tree_str += prefix + ("└── " if is_last_dir else "├── ") + dir_name + "/\n"
        new_prefix = prefix + ("    " if is_last_dir else "│   ")
        tree_str += generate_tree(os.path.join(directory, dir_name), new_prefix, ignore_list)

    # 处理文件
    for i, file_name in enumerate(files):
        is_last = (i == len(files) - 1)
        tree_str += prefix + ("└── " if is_last else "├── ") + file_name + "\n"

    return tree_str


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    project_name = os.path.basename(project_root)

    print(f"正在生成项目结构：{project_name}/\n")

    tree = project_name + "/\n" + generate_tree(project_root)

    # 输出到控制台
    print(tree)

    # 保存到文件
    output_file = "project_structure.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(tree)

    print(f"\n已保存到：{output_file}")


if __name__ == "__main__":
    main()