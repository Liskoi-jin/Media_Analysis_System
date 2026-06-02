// static/js/charts.js

// 图表相关功能

class ChartManager {
    constructor() {
        this.charts = new Map();
        this.defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        font: { size: 12 },
                        color: this.getTextColor()
                    }
                },
                tooltip: {
                    backgroundColor: this.getTooltipBg(),
                    titleColor: this.getTextColor(),
                    bodyColor: this.getTextColor(),
                    borderColor: this.getBorderColor(),
                    borderWidth: 1,
                    padding: 10
                }
            }
        };
    }

    getTextColor() {
        return getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim();
    }

    getTooltipBg() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.95)';
    }

    getBorderColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? 'rgba(99, 102, 241, 0.5)' : 'rgba(67, 97, 238, 0.3)';
    }

    getGridColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
    }

    // 创建柱状图
    createBarChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        const chartOptions = {
            ...this.defaultOptions,
            ...options,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: this.getGridColor() },
                    ticks: { color: this.getTextColor() }
                },
                x: {
                    grid: { color: this.getGridColor() },
                    ticks: { color: this.getTextColor() }
                }
            }
        };

        const chart = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: data,
            options: chartOptions
        });

        this.charts.set(canvasId, chart);
        return chart;
    }

    // 创建折线图
    createLineChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        const chartOptions = {
            ...this.defaultOptions,
            ...options,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: this.getGridColor() },
                    ticks: { color: this.getTextColor() }
                },
                x: {
                    grid: { color: this.getGridColor() },
                    ticks: { color: this.getTextColor() }
                }
            },
            elements: {
                line: { tension: 0.4 }
            }
        };

        const chart = new Chart(ctx.getContext('2d'), {
            type: 'line',
            data: data,
            options: chartOptions
        });

        this.charts.set(canvasId, chart);
        return chart;
    }

    // 创建饼图
    createPieChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        const chartOptions = {
            ...this.defaultOptions,
            ...options,
            plugins: {
                ...this.defaultOptions.plugins,
                legend: {
                    position: 'right',
                    labels: { color: this.getTextColor() }
                }
            }
        };

        const chart = new Chart(ctx.getContext('2d'), {
            type: 'pie',
            data: data,
            options: chartOptions
        });

        this.charts.set(canvasId, chart);
        return chart;
    }

    // 创建环形图
    createDoughnutChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        const chartOptions = {
            ...this.defaultOptions,
            ...options,
            cutout: '70%',
            plugins: {
                ...this.defaultOptions.plugins,
                legend: {
                    position: 'right',
                    labels: { color: this.getTextColor() }
                }
            }
        };

        const chart = new Chart(ctx.getContext('2d'), {
            type: 'doughnut',
            data: data,
            options: chartOptions
        });

        this.charts.set(canvasId, chart);
        return chart;
    }

    // 创建雷达图
    createRadarChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        const chartOptions = {
            ...this.defaultOptions,
            ...options,
            scales: {
                r: {
                    beginAtZero: true,
                    grid: { color: this.getGridColor() },
                    pointLabels: { color: this.getTextColor() },
                    ticks: {
                        color: this.getTextColor(),
                        backdropColor: 'transparent'
                    }
                }
            }
        };

        const chart = new Chart(ctx.getContext('2d'), {
            type: 'radar',
            data: data,
            options: chartOptions
        });

        this.charts.set(canvasId, chart);
        return chart;
    }

    // 创建散点图
    createScatterChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;

        const chartOptions = {
            ...this.defaultOptions,
            ...options,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: this.getGridColor() },
                    ticks: { color: this.getTextColor() }
                },
                x: {
                    beginAtZero: true,
                    grid: { color: this.getGridColor() },
                    ticks: { color: this.getTextColor() }
                }
            }
        };

        const chart = new Chart(ctx.getContext('2d'), {
            type: 'scatter',
            data: data,
            options: chartOptions
        });

        this.charts.set(canvasId, chart);
        return chart;
    }

    // 更新图表数据
    updateChart(canvasId, newData) {
        const chart = this.charts.get(canvasId);
        if (!chart) return;

        chart.data = newData;
        chart.update();
    }

    // 更新图表数据集
    updateChartData(canvasId, datasetIndex, newData) {
        const chart = this.charts.get(canvasId);
        if (!chart) return;

        chart.data.datasets[datasetIndex].data = newData;
        chart.update();
    }

    // 添加数据集
    addDataset(canvasId, dataset) {
        const chart = this.charts.get(canvasId);
        if (!chart) return;

        chart.data.datasets.push(dataset);
        chart.update();
    }

    // 移除数据集
    removeDataset(canvasId, datasetIndex) {
        const chart = this.charts.get(canvasId);
        if (!chart) return;

        chart.data.datasets.splice(datasetIndex, 1);
        chart.update();
    }

    // 销毁图表
    destroyChart(canvasId) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            chart.destroy();
            this.charts.delete(canvasId);
        }
    }

    // 销毁所有图表
    destroyAllCharts() {
        this.charts.forEach((chart, canvasId) => {
            chart.destroy();
        });
        this.charts.clear();
    }

    // 调整图表大小
    resizeChart(canvasId) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            chart.resize();
        }
    }

    // 调整所有图表大小
    resizeAllCharts() {
        this.charts.forEach(chart => {
            chart.resize();
        });
    }

    // 获取图表实例
    getChart(canvasId) {
        return this.charts.get(canvasId);
    }

    // 更新所有图表主题
    updateTheme() {
        this.charts.forEach(chart => {
            if (chart.options.scales) {
                if (chart.options.scales.y) {
                    chart.options.scales.y.grid.color = this.getGridColor();
                    chart.options.scales.y.ticks.color = this.getTextColor();
                }
                if (chart.options.scales.x) {
                    chart.options.scales.x.grid.color = this.getGridColor();
                    chart.options.scales.x.ticks.color = this.getTextColor();
                }
                if (chart.options.scales.r) {
                    chart.options.scales.r.grid.color = this.getGridColor();
                    chart.options.scales.r.pointLabels.color = this.getTextColor();
                    chart.options.scales.r.ticks.color = this.getTextColor();
                }
            }
            if (chart.options.plugins) {
                if (chart.options.plugins.legend) {
                    chart.options.plugins.legend.labels.color = this.getTextColor();
                }
                if (chart.options.plugins.tooltip) {
                    chart.options.plugins.tooltip.backgroundColor = this.getTooltipBg();
                    chart.options.plugins.tooltip.titleColor = this.getTextColor();
                    chart.options.plugins.tooltip.bodyColor = this.getTextColor();
                    chart.options.plugins.tooltip.borderColor = this.getBorderColor();
                }
            }
            chart.update();
        });
    }
}

// 工作量分析图表
class WorkloadCharts {
    constructor() {
        this.manager = new ChartManager();
    }

    createWorkloadOverview(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '总处理量',
                data: data.totalProcessing || [],
                backgroundColor: 'rgba(67, 97, 238, 0.7)',
                borderColor: '#4361ee',
                borderWidth: 1
            }, {
                label: '定档量',
                data: data.scheduledCount || [],
                backgroundColor: 'rgba(6, 214, 160, 0.7)',
                borderColor: '#06d6a0',
                borderWidth: 1
            }]
        };

        return this.manager.createBarChart('workloadOverviewChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '工作量概览',
                    color: this.manager.getTextColor()
                }
            }
        });
    }

    createSchedulingRateChart(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '定档率 (%)',
                data: data.schedulingRates || [],
                backgroundColor: 'rgba(251, 133, 0, 0.1)',
                borderColor: '#fb8b24',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        };

        return this.manager.createLineChart('schedulingRateChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '定档率趋势',
                    color: this.manager.getTextColor()
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            }
        });
    }

    createGradeDistribution(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                data: data.values || [],
                backgroundColor: [
                    'rgba(239, 35, 60, 0.7)',
                    'rgba(6, 214, 160, 0.7)',
                    'rgba(67, 97, 238, 0.7)',
                    'rgba(251, 133, 0, 0.7)'
                ],
                borderColor: [
                    '#ef233c',
                    '#06d6a0',
                    '#4361ee',
                    '#fb8b24'
                ],
                borderWidth: 1
            }]
        };

        return this.manager.createPieChart('gradeDistributionChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '媒介综合评估分布',
                    color: this.manager.getTextColor()
                }
            }
        });
    }

    createGroupComparison(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '小组处理量',
                data: data.groupProcessing || [],
                backgroundColor: 'rgba(114, 9, 183, 0.7)',
                borderColor: '#7209b7',
                borderWidth: 1
            }]
        };

        return this.manager.createBarChart('groupComparisonChart', chartData, {
            indexAxis: 'y',
            plugins: {
                title: {
                    display: true,
                    text: '各小组工作量对比',
                    color: this.manager.getTextColor()
                }
            }
        });
    }
}

// 工作质量分析图表
class QualityCharts {
    constructor() {
        this.manager = new ChartManager();
    }

    createScreeningRateChart(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '过筛率 (%)',
                data: data.screeningRates || [],
                backgroundColor: 'rgba(6, 214, 160, 0.1)',
                borderColor: '#06d6a0',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        };

        return this.manager.createLineChart('screeningRateChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '过筛率趋势',
                    color: this.manager.getTextColor()
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            }
        });
    }

    createQualityAssessmentChart(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                data: data.values || [],
                backgroundColor: [
                    'rgba(6, 214, 160, 0.7)',
                    'rgba(67, 97, 238, 0.7)',
                    'rgba(251, 133, 0, 0.7)',
                    'rgba(239, 35, 60, 0.7)'
                ],
                borderColor: [
                    '#06d6a0',
                    '#4361ee',
                    '#fb8b24',
                    '#ef233c'
                ],
                borderWidth: 1
            }]
        };

        return this.manager.createPieChart('qualityAssessmentChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '工作质量评估分布',
                    color: this.manager.getTextColor()
                }
            }
        });
    }

    createStatusDistribution(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '状态分布',
                data: data.values || [],
                backgroundColor: [
                    'rgba(6, 214, 160, 0.6)',
                    'rgba(67, 97, 238, 0.6)',
                    'rgba(251, 133, 0, 0.6)',
                    'rgba(114, 9, 183, 0.6)',
                    'rgba(239, 35, 60, 0.6)'
                ],
                borderColor: [
                    '#06d6a0',
                    '#4361ee',
                    '#fb8b24',
                    '#7209b7',
                    '#ef233c'
                ],
                borderWidth: 1
            }]
        };

        return this.manager.createBarChart('statusDistributionChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '媒介工作状态分布',
                    color: this.manager.getTextColor()
                }
            }
        });
    }

    createGroupScreeningComparison(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '小组过筛率',
                data: data.groupScreeningRates || [],
                backgroundColor: 'rgba(67, 97, 238, 0.6)',
                borderColor: '#4361ee',
                borderWidth: 1
            }]
        };

        return this.manager.createBarChart('groupScreeningChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '各小组过筛率对比',
                    color: this.manager.getTextColor()
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            }
        });
    }
}

// 成本分析图表
class CostCharts {
    constructor() {
        this.manager = new ChartManager();
    }

    createCostTrendChart(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '平均CPM',
                data: data.cpmValues || [],
                backgroundColor: 'rgba(239, 35, 60, 0.1)',
                borderColor: '#ef233c',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }, {
                label: '平均CPE',
                data: data.cpeValues || [],
                backgroundColor: 'rgba(67, 97, 238, 0.1)',
                borderColor: '#4361ee',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        };

        return this.manager.createLineChart('costTrendChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '成本趋势分析',
                    color: this.manager.getTextColor()
                }
            }
        });
    }

    createRebateDistribution(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '返点比例分布',
                data: data.values || [],
                backgroundColor: 'rgba(251, 133, 0, 0.6)',
                borderColor: '#fb8b24',
                borderWidth: 1
            }]
        };

        return this.manager.createBarChart('rebateDistributionChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '返点比例分布',
                    color: this.manager.getTextColor()
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            }
        });
    }

    createCostStructure(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                data: data.values || [],
                backgroundColor: [
                    'rgba(67, 97, 238, 0.7)',
                    'rgba(6, 214, 160, 0.7)',
                    'rgba(251, 133, 0, 0.7)',
                    'rgba(114, 9, 183, 0.7)',
                    'rgba(239, 35, 60, 0.7)'
                ],
                borderColor: [
                    '#4361ee',
                    '#06d6a0',
                    '#fb8b24',
                    '#7209b7',
                    '#ef233c'
                ],
                borderWidth: 1
            }]
        };

        return this.manager.createPieChart('costStructureChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '成本结构分布',
                    color: this.manager.getTextColor()
                }
            }
        });
    }

    createCostEfficiencyMatrix(data) {
        const chartData = {
            datasets: [{
                label: '媒介成本效益',
                data: data.points || [],
                backgroundColor: data.colors || 'rgba(67, 97, 238, 0.6)',
                borderColor: '#4361ee',
                borderWidth: 1,
                pointRadius: 8
            }]
        };

        return this.manager.createScatterChart('costEfficiencyMatrix', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '成本效益矩阵',
                    color: this.manager.getTextColor()
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const point = context.raw;
                            return `${point.label}: CPM=${point.x}, CPE=${point.y}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    title: {
                        display: true,
                        text: 'CPE (互动成本)',
                        color: this.manager.getTextColor()
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'CPM (千次曝光成本)',
                        color: this.manager.getTextColor()
                    }
                }
            }
        });
    }

    createGroupCostComparison(data) {
        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: '平均CPM',
                data: data.cpmValues || [],
                backgroundColor: 'rgba(239, 35, 60, 0.6)',
                borderColor: '#ef233c',
                borderWidth: 1
            }, {
                label: '平均CPE',
                data: data.cpeValues || [],
                backgroundColor: 'rgba(67, 97, 238, 0.6)',
                borderColor: '#4361ee',
                borderWidth: 1
            }]
        };

        return this.manager.createBarChart('groupCostChart', chartData, {
            plugins: {
                title: {
                    display: true,
                    text: '各小组成本指标对比',
                    color: this.manager.getTextColor()
                }
            }
        });
    }
}

// 全局图表管理器实例
const chartManager = new ChartManager();
const workloadCharts = new WorkloadCharts();
const qualityCharts = new QualityCharts();
const costCharts = new CostCharts();

// 监听主题变化
window.addEventListener('themeChanged', function() {
    chartManager.updateTheme();
});

// 初始化图表
function initializeCharts() {
    window.addEventListener('resize', debounce(() => {
        chartManager.resizeAllCharts();
    }, 250));

    console.log('图表系统初始化完成');
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', initializeCharts);

// 全局导出
window.Charts = {
    manager: chartManager,
    workload: workloadCharts,
    quality: qualityCharts,
    cost: costCharts
};