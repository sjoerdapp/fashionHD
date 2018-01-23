from __future__ import division, print_function

import torch.utils.data as data

#####################################
# BaseDataset Class
#####################################

class BaseDataset(data.Dataset):
    def __init__(self):
        super(BaseDataset, self).__init__()

    def name(self):
        return 'BaseDataset'

    def initialize(self, opt):
        pass


#####################################
# Image Transoform Modules
#####################################

def landmark_to_heatmap(img_sz, lm_label, cloth_type, delta = 15.):
    '''
    Generate a landmark heatmap from landmark coordinates
    Input:
        img_sz (tuple):     size of heatmap in (width, height)
        lm_label (list):    list of (x,y) coordinates. The length depends on the cloth type: 6 for upperbody
                            4 for lowerbody, 8 for fullbody
        cloth_type(int):    1 for upperbody, 2 for lowerbody, 3 for fullbody
        delta:              parameter to adjuct heat extent of each landmark
    Output:
        lm_heatmap (np.ndarray): landmark heatmap of size H x W x C
    '''

    num_channel = 18
    w, h = img_sz
    heatmap = np.zeros((num_channel, h, w), dtype = np.float32)

    x_grid, y_grid = np.meshgrid(range(w), range(h), indexing = 'xy')

    channels = []
    for x_lm, y_lm, v in lm_label:
        if v == 2:
            channel = np.zeros((h, w))
        else:
            channel = np.exp(-((x_grid - x_lm)**2 + (y_grid - y_lm)**2)/(delta**2))
        channels.append(channel)

    channels = np.stack(channels).astype(np.float32)

    if cloth_type == 1:
        assert channels.shape[0] == 6, 'upperbody cloth (1) should have 6 landmarks'
        heatmap[0:6,:] = channels
    elif cloth_type == 2:
        assert channels.shape[0] == 4, 'lowerbody cloth (2) should have 4 landmarks'
        heatmap[6:10,:] = channels
    elif cloth_type == 3:
        assert channels.shape[0] == 8, 'fullbody cloth (3) should have 8 landmarks'
        heatmap[10:18,:] = channels
    else:
        raise ValueError('invalid cloth type %d' % cloth_type)

    return heatmap.transpose([1,2,0]) # transpose to HxWxC



def _trans_resize(img, size):
    '''
    img (np.ndarray): image with arbitrary channels, with size HxWxC
    size (tuple): target size (width, height)
    '''

    return cv2.resize(img, size, interpolation = cv2.INTER_LINEAR)


def _trans_center_crop(img, size):
    '''
    img (np.ndarray): image with arbitrary channels, with size HxWxC
    size (tuple): size of cropped patch (width, height)
    '''
    h, w = img.shape[0:2]
    tw, th = size
    i = int(round((h - th) / 2.))
    j = int(round((w - tw) / 2.))

    return img[i:(i+th), j:(j+tw), :]

def _trans_random_crop(img, size):
    h, w = img.shape[0:2]
    tw, th = size
    i = np.random.randint(0, h-th+1)
    j = np.random.randint(0, w-tw+1)

    return img[i:(i+th), j:(j+tw), :]

def _trans_random_horizontal_flip(img):
    if np.random.rand() >= 0.5:
        return cv2.flip(img, flipCode = 1) # horizontal flip
    else:
        return img

###############################################################################