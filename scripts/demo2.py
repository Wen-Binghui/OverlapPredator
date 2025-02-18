"""
Scripts for pairwise registration demo

Author: Shengyu Huang
Last modified: 22.02.2021
"""
import os, torch, time, shutil, json,glob, sys,copy, argparse, cv2
import numpy as np
from easydict import EasyDict as edict
from torch.utils.data import Dataset
from torch import optim, nn
import open3d as o3d

cwd = os.getcwd()
sys.path.append(cwd)
from datasets.indoor import IndoorDataset
from datasets.dataloader import get_dataloader
from models.architectures import KPFCNN
from lib.utils import load_obj, setup_seed,natural_key, load_config
from lib.benchmark_utils import ransac_pose_estimation, to_o3d_pcd, get_blue, get_yellow, to_tensor
from lib.trainer import Trainer
from lib.loss import MetricLoss
import shutil
setup_seed(0)


class ThreeDMatchDemo(Dataset):
    """
    Load subsampled coordinates, relative rotation and translation
    Output(torch.Tensor):
        src_pcd:        [N,3]
        tgt_pcd:        [M,3]
        rot:            [3,3]
        trans:          [3,1]
    """
    def __init__(self,config, src_path, tgt_path):
        super(ThreeDMatchDemo,self).__init__()
        self.config = config
        self.src_path = src_path
        self.tgt_path = tgt_path

    def __len__(self):
        return 1

    def __getitem__(self,item): 
        # get pointcloud
        src_pcd = torch.load(self.src_path).astype(np.float32)
        tgt_pcd = torch.load(self.tgt_path).astype(np.float32)   
        src_feats=np.ones_like(src_pcd[:,:1]).astype(np.float32)
        tgt_feats=np.ones_like(tgt_pcd[:,:1]).astype(np.float32)

        # fake the ground truth information
        rot = np.eye(3).astype(np.float32)
        trans = np.ones((3,1)).astype(np.float32)
        correspondences = torch.ones(1,2).long()

        return src_pcd, tgt_pcd, src_feats, tgt_feats, rot,trans, correspondences, src_pcd, tgt_pcd, torch.ones(1)



class ThreeDMatchDemo(Dataset):
    """
    Load subsampled coordinates, relative rotation and translation
    Output(torch.Tensor):
        src_pcd:        [N,3]
        tgt_pcd:        [M,3]
        rot:            [3,3]
        trans:          [3,1]
    """
    def __init__(self,config, src_path, tgt_path):
        super(ThreeDMatchDemo,self).__init__()
        self.config = config
        self.src_path = src_path
        self.tgt_path = tgt_path
        
    def __len__(self):
        return 1

    def __getitem__(self, idx): 
        # get pointcloud
        src_pcd = torch.load(self.src_path).astype(np.float32)
        tgt_pcd = torch.load(self.tgt_path).astype(np.float32)   
        src_feats=np.ones_like(src_pcd[:,:1]).astype(np.float32)
        tgt_feats=np.ones_like(tgt_pcd[:,:1]).astype(np.float32)

        # fake the ground truth information
        rot = np.eye(3).astype(np.float32)
        trans = np.ones((3,1)).astype(np.float32)
        correspondences = torch.ones(1,2).long()

        return src_pcd, tgt_pcd, src_feats, tgt_feats, rot,trans, correspondences, src_pcd, tgt_pcd, torch.ones(1)


def lighter(color, percent):
    '''assumes color is rgb between (0, 0, 0) and (1,1,1)'''
    color = np.array(color)
    white = np.array([1, 1, 1])
    vector = white-color
    return color + vector * percent


def draw_registration_result(src_raw, tgt_raw, src_overlap, tgt_overlap, src_saliency, tgt_saliency, tsfm, src_pcd, tgt_pcd):
    ########################################
    # 1. input point cloud
    src_pcd_before = to_o3d_pcd(src_raw)
    tgt_pcd_before = to_o3d_pcd(tgt_raw)
    src_pcd_before.paint_uniform_color(get_yellow())
    tgt_pcd_before.paint_uniform_color(get_blue())
    src_pcd_before.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.3, max_nn=50))
    tgt_pcd_before.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.3, max_nn=50))

    ########################################
    # 2. overlap colors
    rot, trans = to_tensor(tsfm[:3,:3]), to_tensor(tsfm[:3,3][:,None])
    src_overlap = src_overlap[:,None].repeat(1,3).numpy()
    tgt_overlap = tgt_overlap[:,None].repeat(1,3).numpy()
    src_overlap_color = lighter(get_yellow(), 1 - src_overlap)
    tgt_overlap_color = lighter(get_blue(), 1 - tgt_overlap)
    src_pcd_overlap = copy.deepcopy(src_pcd_before)
    src_pcd_overlap.transform(tsfm)
    tgt_pcd_overlap = copy.deepcopy(tgt_pcd_before)
    src_pcd_overlap.colors = o3d.utility.Vector3dVector(src_overlap_color)
    tgt_pcd_overlap.colors = o3d.utility.Vector3dVector(tgt_overlap_color)

    ########################################
    # 3. draw registrations
    src_pcd_after = copy.deepcopy(src_pcd_before)
    src_pcd_after.transform(tsfm)

    vis1 = o3d.visualization.Visualizer()
    vis1.create_window(window_name='Input', width=960, height=540, left=0, top=0)
    vis1.add_geometry(src_pcd_before)
    vis1.add_geometry(tgt_pcd_before)

    vis2 = o3d.visualization.Visualizer()
    vis2.create_window(window_name='Inferred overlap region', width=960, height=540, left=0, top=600)
    vis2.add_geometry(src_pcd_overlap)
    vis2.add_geometry(tgt_pcd_overlap)

    vis3 = o3d.visualization.Visualizer()
    vis3.create_window(window_name ='Our registration', width=960, height=540, left=960, top=0)
    vis3.add_geometry(src_pcd_after)
    vis3.add_geometry(tgt_pcd_before)


    vis4 = o3d.visualization.Visualizer()
    vis4.create_window(window_name ='Corres', width=960, height=540, left=960, top=0)
    vis4.add_geometry(src_pcd)
    vis4.add_geometry(tgt_pcd)
    
    #绘制线条
    src_pcd.transform(tsfm)
    polygon_points = np.concatenate([np.asarray(src_pcd.points), np.asarray(tgt_pcd.points)], axis = 0)
    num_kp = len(src_pcd.points)
    print('num_kp', num_kp)
    lines = [[idx, idx + num_kp] for idx in range(num_kp)]
    color = [[1, 0, 0] for i in range(num_kp)] 
    lines_pcd = o3d.geometry.LineSet()
    lines_pcd.lines = o3d.utility.Vector2iVector(lines)
    lines_pcd.colors = o3d.utility.Vector3dVector(color) #线条颜色
    lines_pcd.points = o3d.utility.Vector3dVector(polygon_points)
    vis3.add_geometry(lines_pcd)

    vis4.add_geometry(lines_pcd)


    while True:
        vis1.update_geometry(src_pcd_before)
        vis1.update_geometry(tgt_pcd_before)
        if not vis1.poll_events():
            break
        vis1.update_renderer()

        vis2.update_geometry(src_pcd_overlap)
        vis2.update_geometry(tgt_pcd_overlap)
        if not vis2.poll_events():
            break
        vis2.update_renderer()

        vis3.update_geometry(src_pcd_after)
        vis3.update_geometry(tgt_pcd_before)
        if not vis3.poll_events():
            break
        vis3.update_renderer()

        vis4.update_geometry(src_pcd)
        vis4.update_geometry(tgt_pcd)
        if not vis4.poll_events():
            break
        vis4.update_renderer()

    vis1.destroy_window()
    vis2.destroy_window()
    vis3.destroy_window()    
    vis4.destroy_window()    

def main(config, demo_loader):
    config.model.eval()
    c_loader_iter = demo_loader.__iter__()
    with torch.no_grad():
        inputs = c_loader_iter.next()
        # print(inputs['stack_lengths'])
        ##################################
        # load inputs to device.
        for k, v in inputs.items():  
            if type(v) == list:
                inputs[k] = [item.to(config.device) for item in v]
            else:
                inputs[k] = v.to(config.device)

        ###############################################
        # forward pass
        feats, scores_overlap, scores_saliency = config.model(inputs)  #[N1, C1], [N2, C2]
        pcd = inputs['points'][0]
        len_src = inputs['stack_lengths'][0][0]
        c_rot, c_trans = inputs['rot'], inputs['trans']
        correspondence = inputs['correspondences']
        
        src_pcd, tgt_pcd = pcd[:len_src], pcd[len_src:]
        src_raw = copy.deepcopy(src_pcd)
        tgt_raw = copy.deepcopy(tgt_pcd)
        src_feats, tgt_feats = feats[:len_src].detach().cpu(), feats[len_src:].detach().cpu()
        src_overlap, src_saliency = scores_overlap[:len_src].detach().cpu(), scores_saliency[:len_src].detach().cpu()
        tgt_overlap, tgt_saliency = scores_overlap[len_src:].detach().cpu(), scores_saliency[len_src:].detach().cpu()

        ########################################
        # do probabilistic sampling guided by the score
        src_scores = src_overlap * src_saliency
        tgt_scores = tgt_overlap * tgt_saliency

        if(src_pcd.size(0) > config.n_points):
            idx = np.arange(src_pcd.size(0))
            probs = (src_scores / src_scores.sum()).numpy().flatten()
            idx = np.random.choice(idx, size= config.n_points, replace=False, p=probs)
            src_pcd, src_feats = src_pcd[idx], src_feats[idx]
        if(tgt_pcd.size(0) > config.n_points):
            idx = np.arange(tgt_pcd.size(0))
            probs = (tgt_scores / tgt_scores.sum()).numpy().flatten()
            idx = np.random.choice(idx, size= config.n_points, replace=False, p=probs)
            tgt_pcd, tgt_feats = tgt_pcd[idx], tgt_feats[idx]

        ########################################
        # run ransac and draw registration
        tsfm = ransac_pose_estimation(src_pcd, tgt_pcd, src_feats, tgt_feats, mutual=False)
        # print(tsfm)
        draw_registration_result(src_raw, tgt_raw, src_overlap, tgt_overlap, src_saliency, tgt_saliency, tsfm)

def one_data(config, inputs):
    config.model.eval()
    with torch.no_grad():
        ##################################
        # load inputs to device.
        for k, v in inputs.items():  
            if type(v) == list:
                try:
                    inputs[k] = [item.to(config.device) for item in v]
                except:
                    print('kk', inputs[k])
            else:
                inputs[k] = v.to(config.device)

        ###############################################
        # forward pass
        feats, scores_overlap, scores_saliency = config.model(inputs)  #[N1, C1], [N2, C2]
        pcd = inputs['points'][0]
        len_src = inputs['stack_lengths'][0][0]
        c_rot, c_trans = inputs['rot'], inputs['trans']
        correspondence = inputs['correspondences']
        
        src_pcd, tgt_pcd = pcd[:len_src], pcd[len_src:]
        src_raw = copy.deepcopy(src_pcd)
        tgt_raw = copy.deepcopy(tgt_pcd)
        src_feats, tgt_feats = feats[:len_src].detach().cpu(), feats[len_src:].detach().cpu()
        src_overlap, src_saliency = scores_overlap[:len_src].detach().cpu(), scores_saliency[:len_src].detach().cpu()
        tgt_overlap, tgt_saliency = scores_overlap[len_src:].detach().cpu(), scores_saliency[len_src:].detach().cpu()

        ########################################
        # do probabilistic sampling guided by the score
        src_scores = src_overlap * src_saliency
        tgt_scores = tgt_overlap * tgt_saliency

        if(src_pcd.size(0) > config.n_points):
            idx = np.arange(src_pcd.size(0))
            probs = (src_scores / src_scores.sum()).numpy().flatten()
            idx = np.random.choice(idx, size= config.n_points, replace=False, p=probs)
            src_pcd, src_feats = src_pcd[idx], src_feats[idx]
        if(tgt_pcd.size(0) > config.n_points):
            idx = np.arange(tgt_pcd.size(0))
            probs = (tgt_scores / tgt_scores.sum()).numpy().flatten()
            idx = np.random.choice(idx, size= config.n_points, replace=False, p=probs)
            tgt_pcd, tgt_feats = tgt_pcd[idx], tgt_feats[idx]

        ########################################
        # run ransac and draw registration
        tsfm, corre_src_pcd, corre_tgt_pcd, src_feat, tgt_feat = ransac_pose_estimation(src_pcd, tgt_pcd, src_feats, tgt_feats, mutual=False)
        # draw_registration_result(src_raw, tgt_raw, src_overlap, tgt_overlap, src_saliency, tgt_saliency, tsfm, corre_src_pcd, corre_tgt_pcd)

        return tsfm, src_pcd, tgt_pcd, corre_src_pcd, corre_tgt_pcd, src_feat, tgt_feat

if __name__ == '__main__':
    # load configs
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=str, help= 'Path to the config file.', default='configs/test/indoor.yaml')
    args = parser.parse_args()
    config = load_config(args.config)
    config = edict(config)
    if config.gpu_mode:
        config.device = torch.device('cuda')
    else:
        config.device = torch.device('cpu')
    
    # model initialization
    config.architecture = [
        'simple',
        'resnetb',
    ]
    for i in range(config.num_layers-1):
        config.architecture.append('resnetb_strided')
        config.architecture.append('resnetb')
        config.architecture.append('resnetb')
    for i in range(config.num_layers-2):
        config.architecture.append('nearest_upsample')
        config.architecture.append('unary')
    config.architecture.append('nearest_upsample')
    config.architecture.append('last_unary')
    config.model = KPFCNN(config).to(config.device)
    
    # create dataset and dataloader
    info_train = load_obj(config.train_info)

    train_set = IndoorDataset(info_train, config, data_augmentation=False)

    demo_loader, neighborhood_limits = get_dataloader(dataset=train_set,
                                        batch_size=1,
                                        shuffle=False,
                                        num_workers=config.num_workers,
                                        )

    # load pretrained weights
    assert config.pretrain != None
    state = torch.load(config.pretrain)
    config.model.load_state_dict(state['state_dict'])


    print('\n\n\n\n\n\n\n\n Start!!!!!!', len(demo_loader))
    dest_folder = 'data/preprocess/predator-nomutual-0514'
    # do pose estimation


    for i, input in enumerate(demo_loader):
        print(info_train['src'][i], info_train['tgt'][i])
        # print(info_train['rot'][i], info_train['trans'][i])
        tsfm, src_pcd, tgt_pcd, corre_src_pcd, corre_tgt_pcd, src_feat, tgt_feat = one_data(config, input)


        id_src = info_train['src'][i].split('bin_')[-1].split('.')[0]
        id_tgt = info_train['tgt'][i].split('bin_')[-1].split('.')[0]
        sub_folder = info_train['src'][i].split('/cloud')[0].split('/')[-1]
        print(id_src, id_tgt, sub_folder)
        save_in_folder = os.path.join(dest_folder, sub_folder)
        if not os.path.exists(save_in_folder):
            os.makedirs(save_in_folder)

        o3d.io.write_point_cloud(os.path.join(save_in_folder, f"{id_src}_{id_tgt}_src.pcd"), corre_src_pcd)
        o3d.io.write_point_cloud(os.path.join(save_in_folder, f"{id_src}_{id_tgt}_tgt.pcd"), corre_tgt_pcd)
        np.save(f"{save_in_folder}/{id_src}_{id_tgt}_feature_src.npy", src_feat)
        np.save(f"{save_in_folder}/{id_src}_{id_tgt}_feature_tgt.npy", tgt_feat)

        gt_ = np.eye(4)
        gt_[:3, :3] = info_train['rot'][i]
        gt_[:3, 3] = info_train['trans'][i].reshape(-1)
        gt_ = np.linalg.inv(gt_)

        cv_file = cv2.FileStorage(f"{save_in_folder}/{id_src}_{id_tgt}.yaml", cv2.FILE_STORAGE_WRITE)
        cv_file.write("transform", gt_)
        cv_file.write("noise_bound", 0.1)
        cv_file.write("src_path", f"{id_src}_{id_tgt}_src.pcd")
        cv_file.write("tgt_path", f"{id_src}_{id_tgt}_tgt.pcd")

    