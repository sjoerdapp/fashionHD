from __future__ import division, print_function
import torch
import torch.nn as nn
from torch.autograd import Variable
from util.timer import Timer

def test_AttributeEncoder():
    from attribute_encoder import AttributeEncoder
    from data.data_loader import CreateDataLoader
    from options.attribute_options import TrainAttributeOptions, TestAttributeOptions

    
    mode = 'train'

    timer = Timer()
    timer.tic()

    if mode == 'train':
        opt = TrainAttributeOptions().parse()
        model = AttributeEncoder()
        model.initialize(opt)

        timer.tic()
        loader = CreateDataLoader(opt)
        loader_iter = iter(loader)
        print('cost %.3f sec to create data loader.' % timer.toc())

        data = loader_iter.next()

        model.set_input(data)
        model.optimize_parameters()
        error = model.get_current_errors()
        print(error)

        model.save_network(model.net, 'AE', 'ep0', model.opt.gpu_ids)

def test_DesignerGAN():
    # from designer_gan_model import DesignerGAN
    from designer_gan_model import DesignerGAN
    from data.data_loader import CreateDataLoader
    from options.gan_options import TrainGANOptions

    opt = TrainGANOptions().parse('--benchmark debug --batch_size 10 --gpu_ids -1')

    loader = CreateDataLoader(opt)
    loader_iter = iter(loader)
    data = loader_iter.next()

    model = DesignerGAN()
    model.initialize(opt)

    model.set_input(data)
    model.forward()

    visuals = model.get_current_visuals()
    for k, v in visuals.iteritems():
        print('%s: (%s) %s' % (k, type(v), v.size()))
    


def test_patchGAN_output_size():
    from networks import NLayerDiscriminator

    input_size = 224
    input = Variable(torch.zeros(1,3,input_size,input_size))
    for n in range(1, 7):
        netD = NLayerDiscriminator(input_nc = 3, ndf = 64, n_layers = n)
        output = netD(input)
        print('n_layers=%d, in_size: %d, out_size: %d' % (n, input_size, output.size(2)))

def test_Unet_size():
    from networks import UnetGenerator
    model = UnetGenerator(input_nc = 3, output_nc = 3, num_downs = 7, ngf=64)
    x = Variable(torch.rand(1,3,224,224))
    y = model(x)



def test_scheduler():
    from options.gan_options import TrainGANOptions
    from models.networks import get_scheduler

    model = nn.Linear(10,10)
    optim = torch.optim.Adam(model.parameters(), lr = 1e-4)
    opt = TrainGANOptions().parse('--gpu_ids -1 --benchmark debug', False, False, False)
    scheduler = get_scheduler(optim, opt)

    for epoch in range(opt.epoch_count, opt.niter + opt.niter_decay + 1):
        scheduler.step()
        print('epoch: %d, lr: %f' % (epoch, optim.param_groups[0]['lr']))


if __name__ == '__main__':
    # test_AttributeEncoder()
    test_patchGAN_output_size()
    # test_DesignerGAN()
    # test_scheduler()
    # test_Unet_size()
