# -*- coding: utf-8 -*-
from __future__ import  absolute_import
import sys
sys.path.append(r"C:\Users\admin\PycharmProjects\pythonProject3\faster-rcnn")
import os
import ipdb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tqdm import tqdm
from utils.config import opt
from data.dataset import Dataset, TestDataset, inverse_normalize
from model.faster_rcnn_vgg16 import FasterRCNNVGG16
from torch.utils import data as data_
from trainer import FasterRCNNTrainer
from utils import array_tool as at
from utils.vis_tool import visdom_bbox
from utils.eval_tool import eval_detection_voc
import numpy as np

def train(**kwargs):
    opt._parse(kwargs)
    dataset = Dataset(opt)
    print('load data')
    dataloader = data_.DataLoader(dataset, batch_size=1,shuffle=True,num_workers=opt.num_workers)
    testset = TestDataset(opt)
    # VOCBboxDataset作为数据读取库，然后依次从样例数据库中读取图片出来，
    test_dataloader = data_.DataLoader(testset,batch_size=1,num_workers=opt.test_num_workers,shuffle=False,pin_memory=True)
    faster_rcnn = FasterRCNNVGG16()
    trainer = FasterRCNNTrainer(faster_rcnn)
    if opt.load_path:
        trainer.load(opt.load_path)
        print('load pretrained model from %s' % opt.load_path)
    trainer.vis.text(dataset.db.label_names, win='labels')
    best_map = 0
    lr_ = opt.lr
    for epoch in range(opt.epoch):
        trainer.reset_meters()
        for ii, (img, bbox_, label_, scale) in tqdm(enumerate(dataloader)):
            scale = at.scalar(scale)
            img, bbox, label = img, bbox_, label_
            trainer.train_step(img, bbox, label, scale)
            if (ii + 1) % opt.plot_every == 0:
                if os.path.exists(opt.debug_file):
                    ipdb.set_trace()
                trainer.vis.plot_many(trainer.get_meter_data())
                ori_img_ = inverse_normalize(at.tonumpy(img[0]))
                gt_img = visdom_bbox(ori_img_,
                                     at.tonumpy(bbox_[0]),
                                     at.tonumpy(label_[0]))
                trainer.vis.img('gt_img', gt_img)
                _bboxes, _labels, _scores = trainer.faster_rcnn.predict([ori_img_], visualize=True)
                pred_img = visdom_bbox(ori_img_,
                                       at.tonumpy(_bboxes[0]),
                                       at.tonumpy(_labels[0]).reshape(-1),
                                       at.tonumpy(_scores[0]))
                trainer.vis.img('pred_img', pred_img)
                _bboxes, _labels, _scores = trainer.faster_rcnn.one_stage_predict([ori_img_], visualize=True)
                one_stage_pred_img = visdom_bbox(ori_img_,
                                       at.tonumpy(_bboxes[0]))
                trainer.vis.img('one_stage_pred_img', one_stage_pred_img)
                trainer.vis.text(str(trainer.rpn_cm.value().tolist()), win='rpn_cm')
                trainer.vis.img('roi_cm', at.totensor(trainer.roi_cm.conf).float())
        eval_result = eval(test_dataloader, faster_rcnn, test_num=4)
        #        eval_result = eval(test_dataloader, faster_rcnn, test_num=opt.test_num)
        trainer.vis.plot('test_map', eval_result['map'])
        lr_ = trainer.faster_rcnn.optimizer.param_groups[0]['lr']
        log_info = 'lr:{}, map:{},loss:{}'.format(str(lr_),
                                                  str(eval_result['map']),
                                                  str(trainer.get_meter_data()))
        trainer.vis.log(log_info)
        if eval_result['map'] > best_map:
            best_map = eval_result['map']
            best_path = trainer.save(best_map=best_map)
        if epoch == 9:
            trainer.load(best_path)
            trainer.faster_rcnn.scale_lr(opt.lr_decay)
            lr_ = lr_ * opt.lr_decay
        if epoch == 13:
            break;

def eval(dataloader, faster_rcnn, test_num=10000):
    pred_bboxes, pred_labels, pred_scores = list(), list(), list()
    gt_bboxes, gt_labels, gt_difficults = list(), list(), list()
    for ii, (imgs, sizes, gt_bboxes_, gt_labels_, gt_difficults_) in tqdm(enumerate(dataloader)):
        sizes = [sizes[0][0].item(), sizes[1][0].item()]
        pred_bboxes_, pred_labels_, pred_scores_ = faster_rcnn.predict(imgs, [sizes])
        gt_bboxes += list(gt_bboxes_.numpy())
        gt_labels += list(gt_labels_.numpy())
        gt_difficults += list(gt_difficults_.numpy())
        pred_bboxes += pred_bboxes_
        pred_labels += pred_labels_
        pred_scores += pred_scores_
        if ii == test_num: break

    result = eval_detection_voc(
        pred_bboxes, pred_labels, pred_scores,
        gt_bboxes, gt_labels, gt_difficults,
        use_07_metric=True)
    return result


if __name__ == '__main__':
    train()
