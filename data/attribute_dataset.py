from __future__ import division

import torchvision.transforms as transforms
from base_dataset import BaseDataset

from PIL import Image
import numpy as np
import os

import util.io as io

class AttributeDataset(BaseDataset):
    
    def name(self):
        return 'AttributeDataset'

    def initialize(self, opt, split):

        self.opt = opt
        self.root = opt.data_root

        # get transform
        transform_list = []

        if opt.resize_or_crop == 'resize':
            # only resize image
            transform_list.append(transforms.Resize(opt.fine_size, Image.BICUBIC))

        elif opt.resize_or_crop == 'resize_and_crop':
            # scale and crop
            transform_list.append(transforms.Resize(opt.load_size, Image.BICUBIC))
            if split == 'train':
                transform_list.append(transforms.RandomCrop(opt.fine_size))
                transform_list.append(transforms.RandomHorizontalFlip())
            else:
                transform_list.append(transforms.CenterCrop(opt.fine_size))

        transform_list.append(transforms.ToTensor())

        if opt.image_normalize == 'imagenet':
            transform_list.append(transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]))
        else:
            transform_list.append(transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]))

        self.transform = transforms.Compose(transform_list)


        # load sample list
        print('loading data ...')
        samples = io.load_json(os.path.join(opt.data_root, opt.fn_sample))
        attr_label = io.load_data(os.path.join(opt.data_root, opt.fn_label))
        attr_entry = io.load_json(os.path.join(opt.data_root, opt.fn_entry))
        attr_split = io.load_json(os.path.join(opt.data_root, opt.fn_split))

        self.id_list = attr_split[split]
        if opt.max_dataset_size != float('inf'):
            self.id_list = self.id_list[0:opt.max_dataset_size]

        self.sample_list = [samples[s_id] for s_id in self.id_list]
        self.attr_label_list = [attr_label[s_id] for s_id in self.id_list]
        self.attr_entry = attr_entry

        if opt.joint_cat:
            cat_label = io.load_data(os.path.join(opt.data_root, opt.fn_cat))
            self.cat_list = [cat_label[s_id] for s_id in self.id_list]

        if opt.unmatch:
            np.random.shuffle(self.sample_list)

        # check data
        assert len(self.attr_entry) == len(self.attr_label_list[0]) == opt.n_attr, 'Attribute number not match!'
        print('dataset created (%d samples)' % len(self))

    def __len__(self):
        return len(self.id_list)

    def __getitem__(self, index):

        s_id = self.id_list[index]
        
        img = Image.open(self.sample_list[index]['img_path']).convert('RGB')
        img = self.transform(img)

        att = np.array(self.attr_label_list[index], dtype = np.float32)

        data = {
            'img': img,
            'att': att,
            'id': s_id
        }

        if self.opt.joint_cat:
            data['cat'] = self.cat_list[index]

        return data

