from __future__ import division, print_function

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
import networks
from misc.image_pool import ImagePool
from misc.color_space import rgb2lab
from misc import pose_util
from base_model import BaseModel
from misc import pose_util

import os
import sys
import numpy as np
import time
from collections import OrderedDict
import argparse
import util.io as io

class VUnetPoseTransferModel(BaseModel):
    def name(self):
        return 'VUnetPoseTransferModel'

    def initialize(self, opt):
        super(VUnetPoseTransferModel, self).initialize(opt)
        ###################################
        # define transformer
        ###################################
        self.netT = networks.VariationalUnet(
            input_nc_dec = self.get_pose_dim(opt.pose_type),
            input_nc_enc = self.get_appearance_dim(opt.appearance_type),
            output_nc = self.get_output_dim(opt.output_type),
            nf = opt.vunet_nf,
            max_nf = opt.vunet_max_nf,
            input_size = opt.fine_size,
            n_latent_scales = opt.vunet_n_latent_scales,
            bottleneck_factor = opt.vunet_bottleneck_factor,
            box_factor = opt.vunet_box_factor,
            n_residual_blocks = 2,
            norm_layer = networks.get_norm_layer(opt.norm),
            activation = nn.ReLU(False),
            use_dropout = False,
            gpu_ids = opt.gpu_ids,
            output_tanh = False,
            )
        if opt.gpu_ids:
            self.netT.cuda()
        networks.init_weights(self.netT, init_type=opt.init_type)
        ###################################
        # define discriminator
        ###################################
        self.use_GAN = self.is_train and opt.loss_weight_gan > 0
        if self.use_GAN:
            self.netD = networks.define_D_from_params(
                input_nc=3+self.get_pose_dim(opt.pose_type) if opt.D_cond else 3,
                ndf=opt.D_nf,
                which_model_netD='n_layers',
                n_layers_D=opt.D_n_layer,
                norm=opt.norm,
                which_gan=opt.which_gan,
                init_type=opt.init_type,
                gpu_ids=opt.gpu_ids)
        else:
            self.netD = None
        ###################################
        # loss functions
        ###################################
        self.crit_psnr = networks.PSNR()
        self.crit_ssim = networks.SSIM()

        if self.is_train:
            self.optimizers =[]
            self.crit_vgg = networks.VGGLoss_v2(self.gpu_ids, opt.content_layer_weight, opt.style_layer_weight, opt.shifted_style)
            # self.crit_vgg_old = networks.VGGLoss(self.gpu_ids)
            self.optim = torch.optim.Adam(self.netT.parameters(), lr=opt.lr, betas=(opt.beta1, opt.beta2), weight_decay=opt.weight_decay)
            self.optimizers += [self.optim]

            if self.use_GAN:
                self.crit_GAN = networks.GANLoss(use_lsgan=opt.which_gan=='lsgan', tensor=self.Tensor)
                self.optim_D = torch.optim.Adam(self.netD.parameters(), lr=opt.lr_D, betas=(opt.beta1, opt.beta2))
                self.optimizers.append(self.optim_D)
            # todo: add pose loss
            self.fake_pool = ImagePool(opt.pool_size)

        ###################################
        # load trained model
        ###################################
        if not self.is_train:
            self.load_network(self.netT, 'netT', opt.which_epoch)
        elif opt.continue_train:
            self.load_network(self.netT, 'netT', opt.which_epoch)
            self.load_optim(self.optim, 'optim', opt.which_epoch)
            if self.use_GAN:
                self.load_network(self.netD, 'netD', opt.which_epoch)
                self.load_optim(self.optim_D, 'optim_D', opt.which_epoch)
        ###################################
        # schedulers
        ###################################
        if self.is_train:
            self.schedulers = []
            for optim in self.optimizers:
                self.schedulers.append(networks.get_scheduler(optim, opt))

    def set_input(self, data):
        input_list = [
            'img_1',
            'joint_1',
            'stickman_1',
            'seg_1',
            'seg_mask_1',

            'img_2',
            'joint_2',
            'stickman_2',
            'seg_2',
            'seg_mask_2',

            # optional
            'limb_1',
            'limb_2',
        ]
        for name in input_list:
            if name in data:
                self.input[name] = self.Tensor(data[name].size()).copy_(data[name])

        self.input['id'] = zip(data['id_1'], data['id_2'])
        self.input['joint_c_1'] = data['joint_c_1']
        self.input['joint_c_2'] = data['joint_c_2']

    def compute_kl_loss(self, ps, qs):
        assert len(ps) == len(qs)
        kl_loss = 0
        for p, q in zip(ps, qs):
            kl_loss += self.netT.latent_kl(p, q)
        return kl_loss

    def forward(self, mode='train'):
        ''' mode in {'train', 'transfer', 'reconstruct_ref'} '''
        if mode == 'reconstruct_ref' or (mode == 'train' and not self.opt.supervised):
            ref_idx = '1'
            tar_idx = '1'
        else:
            ref_idx = '1'
            tar_idx = '2'

        if mode == 'train':
            vunet_mode = 'train'
        else:
            vunet_mode = 'transfer'
        
        appr_ref = self.get_appearance(self.opt.appearance_type, index=ref_idx)
        pose_ref = self.get_pose(self.opt.pose_type, index=ref_idx)
        pose_tar = self.get_pose(self.opt.pose_type, index=tar_idx)
        img_tar = self.input['img_%s'%tar_idx]
        self.output['joint_c_tar'] = self.input['joint_c_%s'%tar_idx]
        self.output['stickman_tar'] = self.input['stickman_%s'%tar_idx]
        self.output['stickman_ref'] = self.input['stickman_%s'%ref_idx]


        netT_output, self.output['ps'], self.output['qs'] = self.netT(appr_ref, pose_ref, pose_tar, vunet_mode)
        netT_output = self.parse_output(netT_output, self.opt.output_type)
        self.output['img_out'] = F.tanh(netT_output['image'])
        self.output['img_tar'] = img_tar
        self.output['pose_tar'] = pose_tar
        self.output['PSNR'] = self.crit_psnr(self.output['img_out'], self.output['img_tar'])
        self.output['SSIM'] = self.Tensor(1).fill_(0) # to save time, do not compute ssim during training
        self.output['seg_ref'] = self.input['seg_%s'%ref_idx] #(bsz, seg_nc, h, w)
        self.output['seg_tar'] = self.input['seg_%s'%tar_idx] #(bsz, seg_nc, h, w)
        if 'seg' in self.opt.output_type:
            self.output['seg_out'] = netT_output['seg'] #(bsz, seg_nc, h, w)
        if 'joint' in self.opt.output_type:
            self.output['joint_out'] = F.sigmoid(netT_output['joint'])
            self.output['joint_tar'] = self.get_pose('joint', index=tar_idx)
            
    def test(self, mode='transfer', compute_loss=False):
        with torch.no_grad():
            self.forward(mode=mode)
        # compute ssim
        self.output['SSIM'] = self.crit_ssim(self.output['img_out'], self.output['img_tar'])
        # compute loss
        if compute_loss:
            self.compute_loss()
        
    def backward_D(self):
        if 'loss_in_lab' in self.opt and self.opt.loss_in_lab:
            # compute loss in Lab space
            lab_out = rgb2lab(self.output['img_out'])
            img_out = ((lab_out[:,0:1]-50.)/50.).repeat(1,3,1,1)

            lab_tar = rgb2lab(self.output['img_tar'])
            img_tar = ((lab_tar[:,0:1]-50.)/50.).repeat(1,3,1,1)
        else:
            # compute loss in RGB space
            img_out = self.output['img_out']
            img_tar = self.output['img_tar']

        if self.opt.D_cond:
            D_input_fake = torch.cat((img_out.detach(), self.output['pose_tar']), dim=1)
            D_input_real = torch.cat((img_tar, self.output['pose_tar']), dim=1)
        else:
            D_input_fake = img_out.detach()
            D_input_real = img_tar

        D_input_fake = self.fake_pool.query(D_input_fake.data)

        loss_D_fake = self.crit_GAN(self.netD(D_input_fake), False)
        loss_D_real = self.crit_GAN(self.netD(D_input_real), True)
        self.output['loss_D'] = 0.5*(loss_D_fake + loss_D_real)
        (self.output['loss_D'] * self.opt.loss_weight_gan).backward()

    def backward(self):
        loss = self.compute_loss()
        loss.backward()

    def compute_loss(self):
        if 'loss_in_lab' in self.opt and self.opt.loss_in_lab:
            # compute loss in Lab space
            lab_out = rgb2lab(self.output['img_out'])
            img_out, color_out = ((lab_out[:,0:1]-50.)/50.).repeat(1,3,1,1), lab_out[:,1:]/100.

            lab_tar = rgb2lab(self.output['img_tar'])
            img_tar, color_tar = ((lab_tar[:,0:1]-50.)/50.).repeat(1,3,1,1), lab_tar[:,1:]/100.
        else:
            # compute loss in RGB space
            img_out = self.output['img_out']
            img_tar = self.output['img_tar']
        
        loss = 0
        # KL
        self.output['loss_kl'] = self.compute_kl_loss(self.output['ps'], self.output['qs'])
        loss += self.output['loss_kl'] * self.opt.loss_weight_kl
        # L1
        self.output['loss_L1'] = F.l1_loss(img_out, img_tar)
        loss += self.output['loss_L1'] * self.opt.loss_weight_L1
        # content
        if self.opt.loss_weight_content > 0:
            self.output['loss_content'] = self.crit_vgg(img_out, img_tar, loss_type='content')
            loss += self.output['loss_content'] * self.opt.loss_weight_content
        # style
        if self.opt.loss_weight_style > 0:
            if self.opt.masked_style:
                mask = self.output['seg_tar'][:,3:5].sum(dim=1, keepdim=True)
            else:
                mask = None
            self.output['loss_style'] = self.crit_vgg(img_out, img_tar, mask, loss_type='style')
            loss += self.output['loss_style'] * self.opt.loss_weight_style
        # local style
        if self.opt.loss_weight_patch_style > 0:
            self.output['loss_patch_style'] = self.compute_patch_style_loss(img_out, self.output['joint_c_tar'], img_tar, self.output['joint_c_tar'], self.opt.patch_size, self.opt.patch_indices_for_loss)
            loss += self.output['loss_patch_style'] * self.opt.loss_weight_patch_style
        # GAN
        if self.use_GAN:
            if self.opt.D_cond:
                D_input = torch.cat((img_out, self.output['pose_tar']), dim=1)
            else:
                D_input = img_out
            self.output['loss_G'] = self.crit_GAN(self.netD(D_input), True)
            loss += self.output['loss_G'] * self.opt.loss_weight_gan
        # seg
        if 'seg' in self.opt.output_type:
            self.output['loss_seg'] = F.cross_entropy(self.output['seg_out'], self.output['seg_tar'].squeeze(dim=1).long())
            loss += self.output['loss_seg'] * self.opt.loss_weight_seg
        # joint
        if 'joint' in self.opt.output_type:
            self.output['loss_joint'] = F.binary_cross_entropy(self.output['joint_out'], self.output['joint_tar'])
            loss += self.output['loss_joint'] * self.opt.loss_weight_joint
        # color (only Lab)
        if 'loss_in_lab' in self.opt and self.opt.loss_in_lab:
            self.output['loss_color'] = F.mse_loss(color_out, color_tar)
            loss += self.output['loss_color'] * self.opt.loss_weight_color

        return loss

    def backward_checkgrad(self):
        if 'loss_in_lab' in self.opt and self.opt.loss_in_lab:
            # compute loss in Lab space
            lab_out = rgb2lab(self.output['img_out'])
            img_out, color_out = ((lab_out[:,0:1]-50.)/50.).repeat(1,3,1,1), lab_out[:,1:]/100.

            lab_tar = rgb2lab(self.output['img_tar'])
            img_tar, color_tar = ((lab_tar[:,0:1]-50.)/50.).repeat(1,3,1,1), lab_tar[:,1:]/100.
        else:
            # compute loss in RGB space
            img_out = self.output['img_out']
            img_tar = self.output['img_tar']

        self.output['img_out'].retain_grad()
        loss = 0
        # L1
        self.output['loss_L1'] = F.l1_loss(img_out, img_tar)
        (self.output['loss_L1'] * self.opt.loss_weight_L1).backward(retain_graph=True)
        self.output['grad_L1'] = self.output['img_out'].grad.norm()
        grad = self.output['img_out'].grad.clone()
        # content 
        if self.opt.loss_weight_content > 0:
            self.output['loss_content'] = self.crit_vgg(img_out, img_tar, loss_type='content')
            (self.output['loss_content'] * self.opt.loss_weight_content).backward(retain_graph=True)
            self.output['grad_content'] = (self.output['img_out'].grad - grad).norm()
            grad = self.output['img_out'].grad.clone()
        # style
        if self.opt.loss_weight_style > 0:
            if self.opt.masked_style:
                mask = self.output['seg_tar'][:,3:5].sum(dim=1, keepdim=True)
            else:
                mask = None
            self.output['loss_style'] = self.crit_vgg(img_out, img_tar, mask, loss_type='style')
            (self.output['loss_style'] * self.opt.loss_weight_style).backward(retain_graph=True)
            self.output['grad_style'] = (self.output['img_out'].grad - grad).norm()
            grad = self.output['img_out'].grad.clone()
        # patch style 
        if self.opt.loss_weight_patch_style > 0:
            self.output['loss_patch_style'] = self.compute_patch_style_loss(img_out, self.output['joint_c_tar'], img_tar, self.output['joint_c_tar'], self.opt.patch_size, self.opt.patch_indices_for_loss)
            (self.output['loss_patch_style'] * self.opt.loss_weight_patch_style).backward(retain_graph=True)
            self.output['grad_patch_style'] = (self.output['img_out'].grad - grad).norm()
            grad = self.output['img_out'].grad.clone()
        # gan 
        if self.use_GAN:
            if self.opt.D_cond:
                D_input = torch.cat((img_out, self.output['pose_tar']), dim=1)
            else:
                D_input = self.output['img_out']
            self.output['loss_G'] = self.crit_GAN(self.netD(D_input), True)
            (self.output['loss_G'] * self.opt.loss_weight_gan).backward(retain_graph=True)
            self.output['grad_gan'] = (self.output['img_out'].grad - grad).norm()
            grad = self.output['img_out'].grad.clone()
        # color
        if 'loss_in_lab' in self.opt and self.opt.loss_in_lab:
            self.output['loss_color'] = F.mse_loss(color_out, color_tar)
            (self.output['loss_color'] * self.opt.loss_weight_color).backward(retain_graph=True)
            self.output['grad_color'] = (self.output['img_out'].grad - grad).norm()
            grad = self.output['img_out'].grad.clone()
        # seg
        if 'seg' in self.opt.output_type:
            self.output['loss_seg'] = F.cross_entropy(self.output['seg_out'], self.output['seg_tar'].squeeze(dim=1).long())
            (self.output['loss_seg'] * self.opt.loss_weight_seg).backward(retain_graph=True)
        # joint
        if 'joint' in self.opt.output_type:
            self.output['loss_joint'] = F.binary_cross_entropy(self.output['joint_out'], self.output['joint_tar'])
            (self.output['loss_joint'] * self.opt.loss_weight_joint).backward(retain_graph=True)
        # KL
        self.output['loss_kl'] = self.compute_kl_loss(self.output['ps'], self.output['qs'])
        (self.output['loss_kl'] * self.opt.loss_weight_kl).backward()

    def optimize_parameters(self, check_grad=False):
        # clear previous output
        self.output = {}
        self.forward()
        if self.use_GAN:
            self.optim_D.zero_grad()
            self.backward_D()
            self.optim_D.step()
        self.optim.zero_grad()
        if check_grad:
            self.backward_checkgrad()
        else:
            self.backward()
        self.optim.step()

    def get_output_dim(self, output_type):
        dim = 0
        output_items = output_type.split('+')
        for item in output_items:
            if item == 'image':
                dim += 3
            elif item == 'seg':
                dim += self.opt.seg_nc
            elif item == 'joint':
                dim += self.opt.joint_nc
            else:
                raise Exception('invalid output type %s'%item)
        return dim

    def parse_output(self, output, output_type):
        assert output.size(1) == self.get_output_dim(output_type)
        output_items = output_type.split('+')
        output_items.sort()
        i = 0
        rst = {}
        for item in output_items:
            if item == 'image':
                rst['image'] = output[:,i:(i+3)]
                i += 3
            elif item == 'seg':
                rst['seg'] = output[:,i:(i+self.opt.seg_nc)]
                # convert raw output to seg_mask
                max_index = rst['seg'].argmax(dim=1)
                seg_mask = []
                for idx in range(self.opt.seg_nc):
                    seg_mask.append(max_index==idx)
                rst['seg_mask'] = torch.stack(seg_mask, dim=1).float()

                i += self.opt.seg_nc
            elif item == 'joint':
                rst['joint'] = output[:,i:(i+self.opt.joint_nc)]
                i += self.opt.joint_nc
            else:
                raise Exception('invalid output type %s'%item)
        return rst

    def get_pose_dim(self, pose_type):
        dim = 0
        pose_items = pose_type.split('+')
        pose_items.sort()
        for item in pose_items:
            if item == 'joint':
                dim += 18
            elif item == 'joint_ext':
                dim += 29
            elif item == 'seg':
                dim += self.opt.seg_nc
            elif item == 'stickman':
                dim += 3
            else:
                raise Exception('invalid pose representation type %s' % item)
        return dim

    def get_pose(self, pose_type, index='1'):
        assert index in {'1', '2'}
        pose = []
        pose_items = pose_type.split('+')
        pose_items.sort()
        for item in pose_items:
            if item == 'joint':
                # joint 0-17 are for pose
                joint_for_pose = self.input['joint_%s'%index][:,0:18]
                pose.append(joint_for_pose)
            elif item == 'joint_ext':
                pose.append(self.input['joint_%s'%index])
            elif item == 'seg':
                pose.append(self.input['seg_mask_%s'%index])
            elif item == 'stickman':
                pose.append(self.input['stickman_%s'%index])
            else:
                raise Exception('invalid pose representation type %s' % item)

        assert len(pose) > 0
        pose = torch.cat(pose, dim=1)
        return pose

    def get_appearance_dim(self, appearance_type):
        dim = 0
        appr_items = appearance_type.split('+')
        for item in appr_items:
            if item == 'image':
                dim += 3
            elif item == 'limb':
                dim += 24 # (3channel x 8limbs)
            else:
                raise Exception('invalid appearance prepresentation type %s'%item)
        return dim
    
    def get_appearance(self, appearance_type, index='1'):
        assert index in {'1', '2'}
        appr = []
        appr_items = appearance_type.split('+')
        for item in appr_items:
            if item == 'image':
                appr.append(self.input['img_%s'%index])
            elif item == 'limb':
                appr.append(self.input['limb_%s'%index])
            else:
                raise Exception('invalid appearance representation type %s' % item)
        assert len(appr) > 0
        appr = torch.cat(appr, dim=1)
        return appr

    def get_patch(self, images, coords, patch_size=32, patch_indices=None):
        '''
        Input:
            image_batch: images (bsz, c, h, w)
            coord: coordinates of joint points (bsz, 18, 2)
        Output:
            patches: (bsz, npatch, c, hp, ww)
        '''
        bsz, c, h, w = images.size()

        # use 0-None for face area, ignore [14-REye, 15-LEye, 16-REar, 17-LEar]
        if patch_indices is None:
            patch_indices = self.opt.patch_indices

        patches = []
        for i in range(bsz):
            patch = []
            img = images[i]
            for j in patch_indices:
                x = int(coords[i,j,0].item())
                y = int(coords[i,j,1].item())

                if x < 0 or y < 0:
                    p = img.new(1, c, patch_size, patch_size).fill_(0)
                else:
                    left    = x-(patch_size//2)
                    right   = x-(patch_size//2)+patch_size
                    top     = y-(patch_size//2)
                    bottom  = y-(patch_size//2)+patch_size

                    left, p_l   = (left, 0) if left >= 0 else (0, -left)
                    right, p_r  = (right, 0) if right <= w else (w, right-w)
                    top, p_t    = (top, 0) if top >= 0 else (0, -top)
                    bottom, p_b = (bottom, 0) if bottom <= h else (h, bottom-h)

                    p = img[:, top:bottom, left:right].unsqueeze(dim=0)
                    if not (p_l == p_r == p_t == p_b == 0):
                        p = F.pad(p, pad=(p_l, p_r, p_t, p_b), mode='constant')
                patch.append(p)
            patch = torch.cat(patch, dim=0)#[npatch, c, hp, wp]
            patches.append(patch)
        patches = torch.stack(patches)#[bsz, npatch, c, hp, wp]

        return patches

    def compute_patch_style_loss(self, images_1, coords_1, images_2, coords_2, patch_size=32, patch_indices=None):
        '''
        images_1: (bsz, h, w, h)
        images_2: (bsz, h, w, h)
        coords_1: (bsz, 18, 2) # patch center coordinates of images_1
        coords_2: (bsz, 18, 2) # patch center coordinates of images_2
        '''
        # remove invalid joint point
        c_invalid = (coords_1 < 0) | (coords_2 < 0)
        vc_1 = coords_1.clone()
        vc_2 = coords_2.clone()
        vc_1[c_invalid] = -1
        vc_2[c_invalid] = -1
        # get patches
        patches_1 = self.get_patch(images_1, vc_1, patch_size, patch_indices) # list: [patch_c1, patch_c2, ...]
        patches_2 = self.get_patch(images_2, vc_2, patch_size, patch_indices)
        # compute style loss
        bsz, npatch, c, h, w = patches_1.size()
        patches_1 = patches_1.view(bsz*npatch, c, h, w)
        patches_2 = patches_2.view(bsz*npatch, c, h, w)
        loss_patch_style = self.crit_vgg(patches_1, patches_2, loss_type='style')

        # output = {
        #     'images_1': images_1.cpu(),
        #     'images_2': images_2.cpu(),
        #     'coords_1': coords_1.cpu(),
        #     'coords_2': coords_2.cpu(),
        #     'patches_1': patches_1.cpu(),
        #     'patches_2': patches_2.cpu(),
        #     'npatch': npatch,
        #     'id': self.input['id']
        # }

        # torch.save(output, 'data.pth')
        # exit()
        return loss_patch_style

    def batch_scale_alignment(self, images, pose, pose_std):
        '''
        resize image to proper scale according to its pose coordinates and target pose coordinates.
        Input:
            images: (bsz, h, w, h)
            pose:   (bsz, 18, 2)
            pose_std: (bsz, 18, 2)
        Output:
            images_out: (bsz, h, w, h)
            pose_out: (bsz, 18, 2)
        '''
        # bsz, c, h, w = images.size()
        # pose_np = pose.cpu().numpy()
        # pose_std_np = pose_std.cpu().numpy()

        # images_out = []
        # pose_out = []
        pass



    def get_current_errors(self):
        error_list = ['PSNR', 'SSIM', 'loss_L1', 'loss_content', 'loss_style', 'loss_patch_style', 'loss_kl', 'loss_G', 'loss_D', 'loss_seg', 'loss_joint', 'loss_color', 'grad_L1', 'grad_content', 'grad_style', 'grad_patch_style', 'grad_gan', 'grad_color']
        errors = OrderedDict()
        for item in error_list:
            if item in self.output:
                errors[item] = self.output[item].data.item()
        return errors

    def get_current_visuals(self):
        visuals = OrderedDict([
            ('img_ref', [self.input['img_1'].data.cpu(), 'rgb']),
            ('stickman_ref', [self.output['stickman_ref'].data.cpu(), 'rgb']),
            ('stickman_tar', [self.output['stickman_tar'].data.cpu(), 'rgb']),
            ('img_tar', [self.output['img_tar'].data.cpu(), 'rgb']),
            ('img_out', [self.output['img_out'].data.cpu(), 'rgb']),
            ])
        if 'seg' in self.opt.output_type:
            visuals['seg_ref'] = [self.output['seg_ref'], 'seg']
            visuals['seg_tar'] = [self.output['seg_tar'], 'seg']
            visuals['seg_out'] = [self.output['seg_out'], 'seg']
        if 'joint' in self.opt.output_type:
            visuals['joint_tar'] = [self.output['joint_tar'], 'pose']
            visuals['joint_out'] = [self.output['joint_out'], 'pose']
        return visuals

    def save(self, label):
        self.save_network(self.netT, 'netT', label, self.gpu_ids)
        if self.use_GAN:
            self.save_network(self.netD, 'netD', label, self.gpu_ids)
        if self.is_train:
            self.save_optim(self.optim, 'optim', label)
            if self.use_GAN:
                self.save_optim(self.optim_D, 'optim_D', label)


