# -*- coding=utf-8 -*-
import warnings
import numpy as np
import pandas as pd
import os
import mne

# 确保 MNE 数据目录存在
mne_data_dir = os.path.join(os.path.expanduser("~"), "mne_data")
if not os.path.exists(mne_data_dir):
    os.makedirs(mne_data_dir)
    print(f"已创建目录: {mne_data_dir}")

# 数据处理和机器学习相关库
from sklearn.pipeline import make_pipeline
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
from mne.decoding import CSP

# MOABB核心组件：用于加载数据集、定义任务范式和进行评估
from moabb.datasets import BNCI2014_001
from moabb.paradigms import LeftRightImagery
from moabb.evaluations import WithinSessionEvaluation

# 忽略可能出现的警告，让输出更清爽
warnings.filterwarnings('ignore')

# 创建CSP+LDA的流水线
# n_components=8：选择8个最优的空间滤波组件，这是一个在论文中常用的经验值[reference:4]
# log=True：在特征提取时自动应用对数运算，使数据分布更稳健[reference:5]
pipelines = {}
pipelines["CSP+LDA"] = make_pipeline(
    CSP(n_components=8, log=True),
    LDA(solver='lsqr', shrinkage='auto')  # 实现自动正则化，也叫 "shrinkage"，有助于提高在小数据集上的性能和稳定性[reference:6]
)

# 定义“左右手运动想象”任务范式，将原始信号裁剪成多个试次[reference:10]
paradigm = LeftRightImagery()

# 加载BNCI2014-001数据集，它包含了9位受试者的记录[reference:11]
dataset = BNCI2014_001()

# 创建评估对象：在单个session内在同一受试者上进行交叉验证，确保公平性和统计可靠性[reference:12]
evaluation = WithinSessionEvaluation(
    paradigm=paradigm,
    datasets=[dataset],
    overwrite=True,
    random_state=42
)

# 运行评估流程，这会自动处理数据下载、预处理、特征提取、分类和交叉验证
results = evaluation.process(pipelines)

# 输出评估结果的关键列，用于查看模型性能
print("评估结果的关键列：", results.columns.tolist())

# 按受试者分组，并计算每个受试者的平均得分，以了解模型在不同个体上的稳定性
print("\n每位受试者的平均准确率：")
print(results.groupby('subject')['score'].mean().to_string())

# 计算并打印总体平均准确率和标准差，这是你后续改进的基线
mean_accuracy = results['score'].mean() * 100
std_accuracy = results['score'].std() * 100
print(f"\n总体平均准确率: {mean_accuracy:.2f}% (±{std_accuracy:.2f}%)")
print("\n你的基线模型已成功跑通！")