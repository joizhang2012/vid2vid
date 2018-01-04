import torch
import torch.nn as nn
from torch.nn import init
import functools
import torch.nn.functional as F
from torch.autograd import Variable
from torch.optim import lr_scheduler


###############################################################################
# Functions
###############################################################################

def weights_init_normal(m):
    classname = m.__class__.__name__
    # print(classname)
    if classname.find('Conv') != -1:
        init.uniform(m.weight.data, 0.0, 0.02)
    elif classname.find('Linear') != -1:
        init.uniform(m.weight.data, 0.0, 0.02)
    elif classname.find('BatchNorm2d') != -1:
        init.uniform(m.weight.data, 1.0, 0.02)
        init.constant(m.bias.data, 0.0)


def weights_init_xavier(m):
    classname = m.__class__.__name__
    # print(classname)
    if classname.find('Conv') != -1:
        init.xavier_normal(m.weight.data, gain=1)
    elif classname.find('Linear') != -1:
        init.xavier_normal(m.weight.data, gain=1)
    elif classname.find('BatchNorm2d') != -1:
        init.uniform(m.weight.data, 1.0, 0.02)
        init.constant(m.bias.data, 0.0)


def weights_init_kaiming(m):
    classname = m.__class__.__name__
    # print(classname)
    if classname.find('Conv') != -1:
        init.kaiming_normal(m.weight.data, a=0, mode='fan_in')
    elif classname.find('Linear') != -1:
        init.kaiming_normal(m.weight.data, a=0, mode='fan_in')
    elif classname.find('BatchNorm2d') != -1:
        init.uniform(m.weight.data, 1.0, 0.02)
        init.constant(m.bias.data, 0.0)


def weights_init_orthogonal(m):
    classname = m.__class__.__name__
    print(classname)
    if classname.find('Conv') != -1:
        init.orthogonal(m.weight.data, gain=1)
    elif classname.find('Linear') != -1:
        init.orthogonal(m.weight.data, gain=1)
    elif classname.find('BatchNorm2d') != -1:
        init.uniform(m.weight.data, 1.0, 0.02)
        init.constant(m.bias.data, 0.0)


def init_weights(net, init_type='normal'):
    print('initialization method [%s]' % init_type)
    if init_type == 'normal':
        net.apply(weights_init_normal)
    elif init_type == 'xavier':
        net.apply(weights_init_xavier)
    elif init_type == 'kaiming':
        net.apply(weights_init_kaiming)
    elif init_type == 'orthogonal':
        net.apply(weights_init_orthogonal)
    else:
        raise NotImplementedError('initialization method [%s] is not implemented' % init_type)


## 3D Change
def get_norm_layer(norm_type='instance'):
    ## BatchNorm3D, InstanceNorm3d
    if norm_type == 'batch':
        norm_layer = functools.partial(nn.BatchNorm3d, affine=True)
    elif norm_type == 'instance':
        norm_layer = functools.partial(nn.InstanceNorm3d, affine=False)
    elif norm_type == 'none':  # fix
        norm_layer = None
    else:
        raise NotImplementedError('normalization layer [%s] is not found' % norm_type)
    return norm_layer


def get_scheduler(optimizer, opt):
    if opt.lr_policy == 'lambda':
        def lambda_rule(epoch):
            lr_l = 1.0 - max(0, epoch + 1 + opt.epoch_count - opt.niter) / float(opt.niter_decay + 1)
            return lr_l

        scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda_rule)
    elif opt.lr_policy == 'step':
        scheduler = lr_scheduler.StepLR(optimizer, step_size=opt.lr_decay_iters, gamma=0.1)
    elif opt.lr_policy == 'plateau':
        scheduler = lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.2, threshold=0.01, patience=5)
    else:
        return NotImplementedError('learning rate policy [%s] is not implemented', opt.lr_policy)
    return scheduler


def define_encoder(input_nc, output_nc, ngf, which_model_encoder, norm='batch', use_dropout=False, init_type='normal',
             gpu_ids=[]):
    encoder = None
    use_gpu = len(gpu_ids) > 0
    norm_layer = get_norm_layer(norm_type=norm)

    if use_gpu:
        assert (torch.cuda.is_available())
    if which_model_encoder == "ResnetVideoEncoder":
        encoder = ResnetVideoEncoder(input_nc, output_nc, ngf, norm_layer=norm_layer, use_dropout=use_dropout, 
                                    n_blocks=6, gpu_ids=gpu_ids)
    else:
        raise NotImplementedError('Video encoder model name [%s] is not recognized' % which_model_encoder)
    if use_gpu > 0:
        encoder.cuda(gpu_ids[0])
    init_weights(encoder, init_type=init_type)
    return encoder


"""
TODO separate Gnerator from video encoder - feature extractor
"""
def define_G(input_nc, output_nc, ngf, which_model_netG, norm='batch', use_dropout=False, init_type='normal',
             gpu_ids=[], input_height=None, input_width=None, sequence_dim=None):
    netG = None
    use_gpu = len(gpu_ids) > 0
    norm_layer = get_norm_layer(norm_type=norm)

    if use_gpu:
        assert (torch.cuda.is_available())

    if which_model_netG == 'resnet_9blocks':
        netG = ResnetGenerator(input_nc, output_nc, ngf, norm_layer=norm_layer, use_dropout=use_dropout, n_blocks=9,
                               gpu_ids=gpu_ids)
    elif which_model_netG == 'resnet_6blocks':
        netG = ResnetGenerator(input_nc, output_nc, ngf, norm_layer=norm_layer, use_dropout=use_dropout, n_blocks=6,
                               gpu_ids=gpu_ids)
    elif which_model_netG == 'unet_128':
        netG = UnetGenerator(input_nc, output_nc, 7, ngf, norm_layer=norm_layer, use_dropout=use_dropout,
                             gpu_ids=gpu_ids)
    elif which_model_netG == 'unet_256':
        netG = UnetGenerator(input_nc, output_nc, 8, ngf, norm_layer=norm_layer, use_dropout=use_dropout,
                             gpu_ids=gpu_ids)
    elif which_model_netG == 'SensorGenerator':
        netG = SensorGenerator(input_nc, output_nc, ngf, norm_layer=norm_layer, use_dropout=use_dropout, n_blocks=1,
                               gpu_ids=gpu_ids)
    elif which_model_netG == 'SequenceGenerator':
        netG = SequenceGenerator(input_nc, output_nc, rnn_input_size=196608, norm_layer=norm_layer, ngf=ngf,
                                 use_dropout=use_dropout, n_blocks=1, gpu_ids=gpu_ids)
    elif which_model_netG == 'SeqCNNGenerator':
        if input_height is None or input_width is None or sequence_dim is None:
            raise ValueError('Params input_height, input_width and sequence_dim is necessary.')
        netG = SeqCNNGenerator(input_nc, output_nc, ngf=ngf, norm_layer=norm_layer,
                                 use_dropout=use_dropout, n_blocks=2, gpu_ids=gpu_ids, 
                                 input_height=input_height, input_width=input_width, sequence_dim=sequence_dim)
    elif which_model_netG == 'ResnetVideoGenerator':
        netG = ResnetVideoGenerator(input_nc, output_nc, ngf=ngf, norm_layer=norm_layer,
                                 use_dropout=use_dropout, n_blocks=2, gpu_ids=gpu_ids)
    else:
        raise NotImplementedError('Generator model name [%s] is not recognized' % which_model_netG)
    if len(gpu_ids) > 0:
        netG.cuda(gpu_ids[0])
    init_weights(netG, init_type=init_type)
    return netG


def define_D(input_nc, ngf, which_model_netD, n_layers_D=3, norm='batch', use_sigmoid=False,
            init_type='normal', gpu_ids=[], sequence_dim=None, sequence_depth=None):
    netD = None
    use_gpu = len(gpu_ids) > 0
    norm_layer = get_norm_layer(norm_type=norm)

    if use_gpu:
        assert (torch.cuda.is_available())
    if which_model_netD == 'basic':
        netD = NLayerDiscriminator(input_nc, ngf, n_layers=3, norm_layer=norm_layer, use_sigmoid=use_sigmoid,
                                   gpu_ids=gpu_ids)
    elif which_model_netD == 'n_layers':
        netD = NLayerDiscriminator(input_nc, ngf, n_layers_D, norm_layer=norm_layer, use_sigmoid=use_sigmoid,
                                   gpu_ids=gpu_ids)
    elif which_model_netD == 'SequenceDiscriminator':
        netD = SequenceDiscriminator(input_size=1, gpu_ids=gpu_ids)
    elif which_model_netD == 'SeqCNNDiscriminator':
        if sequence_dim is None or sequence_depth is None:
            raise ValueError('Specify sequence_dim and sequence_depth when use conv seq discriminator.')
        netD = SeqCNNDiscriminator(input_depth=sequence_depth, input_dim=sequence_dim, 
            ngf=ngf, gpu_ids=gpu_ids)
    else:
        raise NotImplementedError('Discriminator model name [%s] is not recognized' %
                                  which_model_netD)
    if use_gpu:
        netD.cuda(gpu_ids[0])
    init_weights(netD, init_type=init_type)
    return netD


def print_network(net):
    num_params = 0
    for param in net.parameters():
        num_params += param.numel()
    print(net)
    print('Total number of parameters: %d' % num_params)


##############################################################################
# Classes
##############################################################################


# Defines the GAN loss which uses either LSGAN or the regular GAN.
# When LSGAN is used, it is basically same as MSELoss,
# but it abstracts away the need to create the target label tensor
# that has the same size as the input
class GANLoss(nn.Module):
    def __init__(self, use_lsgan=True, target_real_label=1.0, target_fake_label=0.0,
                 tensor=torch.FloatTensor):
        super(GANLoss, self).__init__()
        self.real_label = target_real_label
        self.fake_label = target_fake_label
        self.real_label_var = None
        self.fake_label_var = None
        self.Tensor = tensor
        if use_lsgan:
            self.loss = nn.MSELoss()
        else:
            self.loss = nn.BCELoss()

    def get_target_tensor(self, input, target_is_real):
        target_tensor = None
        if target_is_real:
            create_label = ((self.real_label_var is None) or
                            (self.real_label_var.numel() != input.numel()))
            if create_label:
                real_tensor = self.Tensor(input.size()).fill_(self.real_label)
                self.real_label_var = Variable(real_tensor, requires_grad=False)
            target_tensor = self.real_label_var
        else:
            create_label = ((self.fake_label_var is None) or
                            (self.fake_label_var.numel() != input.numel()))
            if create_label:
                fake_tensor = self.Tensor(input.size()).fill_(self.fake_label)
                self.fake_label_var = Variable(fake_tensor, requires_grad=False)
            target_tensor = self.fake_label_var
        return target_tensor

    def __call__(self, input, target_is_real):
        target_tensor = self.get_target_tensor(input, target_is_real)
        return self.loss(input, target_tensor)


# Defines the generator that consists of Resnet blocks between a few
# downsampling/upsampling operations.
# Code and idea originally from Justin Johnson's architecture.
# https://github.com/jcjohnson/fast-neural-style/
class ResnetGenerator(nn.Module):
    def __init__(self, input_nc, output_nc, ngf=64, norm_layer=nn.BatchNorm2d, use_dropout=False, n_blocks=6,
                 gpu_ids=[], padding_type='reflect'):
        assert (n_blocks >= 0)
        super(ResnetGenerator, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.ngf = ngf
        self.gpu_ids = gpu_ids
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm2d
        else:
            use_bias = norm_layer == nn.InstanceNorm2d

        model = [nn.ReflectionPad2d(3),
                 nn.Conv2d(input_nc, ngf, kernel_size=7, padding=0,
                           bias=use_bias),
                 norm_layer(ngf),
                 nn.ReLU(True)]

        n_downsampling = 2
        for i in range(n_downsampling):
            mult = 2 ** i
            model += [nn.Conv2d(ngf * mult, ngf * mult * 2, kernel_size=3,
                                stride=2, padding=1, bias=use_bias),
                      norm_layer(ngf * mult * 2),
                      nn.ReLU(True)]

        mult = 2 ** n_downsampling
        for i in range(n_blocks):
            model += [ResnetBlock(ngf * mult, padding_type=padding_type, norm_layer=norm_layer, use_dropout=use_dropout,
                                  use_bias=use_bias)]
        for i in range(n_downsampling):
            mult = 2 ** (n_downsampling - i)
            model += [nn.ConvTranspose2d(ngf * mult, int(ngf * mult / 2),
                                         kernel_size=3, stride=2,
                                         padding=1, output_padding=1,
                                         bias=use_bias),
                      norm_layer(int(ngf * mult / 2)),
                      nn.ReLU(True)]
        model += [nn.ReflectionPad2d(3)]
        model += [nn.Conv2d(ngf, output_nc, kernel_size=7, padding=0)]
        model += [nn.Tanh()]

        self.model = nn.Sequential(*model)

    def forward(self, input):
        if self.gpu_ids and isinstance(input.data, torch.cuda.FloatTensor):
            return nn.parallel.data_parallel(self.model, input, self.gpu_ids)
        else:
            return self.model(input)


# Define a resnet block
class ResnetBlock(nn.Module):
    def __init__(self, dim, padding_type, norm_layer, use_dropout, use_bias):
        super(ResnetBlock, self).__init__()
        self.conv_block = self.build_conv_block(dim, padding_type, norm_layer, use_dropout, use_bias)

    def build_conv_block(self, dim, padding_type, norm_layer, use_dropout, use_bias):
        conv_block = []
        p = 0
        if padding_type == 'reflect':
            conv_block += [nn.ReflectionPad2d(1)]
        elif padding_type == 'replicate':
            conv_block += [nn.ReplicationPad2d(1)]
        elif padding_type == 'zero':
            p = 1
        else:
            raise NotImplementedError('padding [%s] is not implemented' % padding_type)

        conv_block += [nn.Conv2d(dim, dim, kernel_size=3, padding=p, bias=use_bias),
                       norm_layer(dim),
                       nn.ReLU(True)]
        if use_dropout:
            conv_block += [nn.Dropout(0.5)]

        p = 0
        if padding_type == 'reflect':
            conv_block += [nn.ReflectionPad2d(1)]
        elif padding_type == 'replicate':
            conv_block += [nn.ReplicationPad2d(1)]
        elif padding_type == 'zero':
            p = 1
        else:
            raise NotImplementedError('padding [%s] is not implemented' % padding_type)
        conv_block += [nn.Conv2d(dim, dim, kernel_size=3, padding=p, bias=use_bias),
                       norm_layer(dim)]

        return nn.Sequential(*conv_block)

    def forward(self, x):
        out = x + self.conv_block(x)
        return out


# Defines the Unet generator.
# |num_downs|: number of downsamplings in UNet. For example,
# if |num_downs| == 7, image of size 128x128 will become of size 1x1
# at the bottleneck

## 3D Change
class UnetGenerator(nn.Module):
    def __init__(self, input_nc, output_nc, num_downs, ngf=64,
                 norm_layer=nn.BatchNorm3d, use_dropout=False, gpu_ids=[]):
        super(UnetGenerator, self).__init__()
        self.gpu_ids = gpu_ids

        # construct unet structure
        unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=None, norm_layer=norm_layer,
                                             innermost=True)
        for i in range(num_downs - 5):
            unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=unet_block,
                                                 norm_layer=norm_layer, use_dropout=use_dropout)
        unet_block = UnetSkipConnectionBlock(ngf * 4, ngf * 8, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(ngf * 2, ngf * 4, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(ngf, ngf * 2, input_nc=None, submodule=unet_block, norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(output_nc, ngf, input_nc=input_nc, submodule=unet_block, outermost=True,
                                             norm_layer=norm_layer)

        self.model = unet_block

    def forward(self, input):
        if self.gpu_ids and isinstance(input.data, torch.cuda.FloatTensor):
            return nn.parallel.data_parallel(self.model, input, self.gpu_ids)
        else:
            return self.model(input)


# Defines the submodule with skip connection.
# X -------------------identity---------------------- X
#   |-- downsampling -- |submodule| -- upsampling --|

## 3D Change
class UnetSkipConnectionBlock(nn.Module):
    def __init__(self, outer_nc, inner_nc, input_nc=None,
                 submodule=None, outermost=False, innermost=False, norm_layer=nn.BatchNorm3d, use_dropout=False):
        super(UnetSkipConnectionBlock, self).__init__()
        self.outermost = outermost
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm3d
        else:
            use_bias = norm_layer == nn.InstanceNorm3d
        if input_nc is None:
            input_nc = outer_nc
        kw = (3, 4, 4)
        s = (1, 2, 2)
        downconv = nn.Conv3d(input_nc, inner_nc, kernel_size=kw,
                             stride=s, padding=1, bias=use_bias)
        downrelu = nn.LeakyReLU(0.2, True)
        downnorm = norm_layer(inner_nc)
        uprelu = nn.ReLU(True)
        upnorm = norm_layer(outer_nc)

        if outermost:
            upconv = nn.ConvTranspose3d(inner_nc * 2, outer_nc, kernel_size=kw, stride=s,
                                        padding=1)
            down = [downconv]
            up = [uprelu, upconv, nn.Tanh()]
            model = down + [submodule] + up
        elif innermost:
            upconv = nn.ConvTranspose3d(inner_nc, outer_nc,
                                        kernel_size=kw, stride=s,
                                        padding=1, bias=use_bias)
            down = [downrelu, downconv]
            up = [uprelu, upconv, upnorm]
            model = down + up
        else:
            upconv = nn.ConvTranspose3d(inner_nc * 2, outer_nc,
                                        kernel_size=kw, stride=s,
                                        padding=1, bias=use_bias)
            down = [downrelu, downconv, downnorm]
            up = [uprelu, upconv, upnorm]

            if use_dropout:
                model = down + [submodule] + up + [nn.Dropout(0.5)]
            else:
                model = down + [submodule] + up

        self.model = nn.Sequential(*model)

    def forward(self, x):
        if self.outermost:
            return self.model(x)
        else:
            return torch.cat([x, self.model(x)], 1)


'''
    2dcnn Shape:
        - Input: :math:`(N, C_{in}, H_{in}, W_{in})`
        - Output: :math:`(N, C_{out}, H_{out}, W_{out})` where
          :math:`H_{out} = (H_{in} - 1) * stride[0] - 2 * padding[0] + kernel\_size[0] + output\_padding[0]`
          :math:`W_{out} = (W_{in} - 1) * stride[1] - 2 * padding[1] + kernel\_size[1] + output\_padding[1]`
    3dcnn Shape:
        - Input: :math:`(N, C_{in}, D_{in}, H_{in}, W_{in})`
        - Output: :math:`(N, C_{out}, D_{out}, H_{out}, W_{out})` where
          :math:`D_{out} = (D_{in} - 1) * stride[0] - 2 * padding[0] + kernel\_size[0] + output\_padding[0]`
          :math:`H_{out} = (H_{in} - 1) * stride[1] - 2 * padding[1] + kernel\_size[1] + output\_padding[1]`
          :math:`W_{out} = (W_{in} - 1) * stride[2] - 2 * padding[2] + kernel\_size[2] + output\_padding[2]`
'''


# Defines the PatchGAN discriminator with the specified arguments.
class NLayerDiscriminator(nn.Module):
    def __init__(self, input_nc, ngf=64, n_layers=3, norm_layer=nn.BatchNorm3d, use_sigmoid=False, gpu_ids=[]):
        super(NLayerDiscriminator, self).__init__()
        self.gpu_ids = gpu_ids
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm3d
        else:
            use_bias = norm_layer == nn.InstanceNorm3d

        ## TODO: D kernel 4
        kw = [3, 4, 4]
        padw = 1
        # s = [1, 2, 2]
        sequence = [
            nn.Conv3d(input_nc, ngf, kernel_size=kw, stride=(1, 2, 2), padding=padw),
            nn.LeakyReLU(0.2, True)
        ]

        nf_mult = 1
        nf_mult_prev = 1
        for n in range(1, n_layers):
            nf_mult_prev = nf_mult
            nf_mult = min(2 ** n, 8)
            print("===================" + str(2 ** n))
            sequence += [
                nn.Conv3d(ngf * nf_mult_prev, ngf * nf_mult,
                          kernel_size=kw, stride=(1, 2, 2), padding=padw, bias=use_bias),
                norm_layer(ngf * nf_mult),
                nn.LeakyReLU(0.2, True)
            ]

        nf_mult_prev = nf_mult
        nf_mult = min(2 ** n_layers, 8)
        sequence += [
            nn.Conv3d(ngf * nf_mult_prev, ngf * nf_mult,
                      kernel_size=kw, stride=1, padding=padw, bias=use_bias),
            norm_layer(ngf * nf_mult),
            nn.LeakyReLU(0.2, True)
        ]

        sequence += [nn.Conv3d(ngf * nf_mult, 1, kernel_size=kw, stride=1, padding=padw)]

        if use_sigmoid:
            sequence += [nn.Sigmoid()]

        self.model = nn.Sequential(*sequence)

    def forward(self, input):
        if len(self.gpu_ids) and isinstance(input.data, torch.cuda.FloatTensor):
            return nn.parallel.data_parallel(self.model, input, self.gpu_ids)
        else:
            return self.model(input)


# Define a resnet block
class ResnetBlock_3d(nn.Module):
    def __init__(self, dim, padding_type, norm_layer, use_dropout, use_bias):
        super(ResnetBlock_3d, self).__init__()
        self.conv_block = self.build_conv_block(dim, padding_type, norm_layer, use_dropout, use_bias)

    def build_conv_block(self, dim, padding_type, norm_layer, use_dropout, use_bias):
        conv_block = []
        p = 1
        kw = [3, 3, 3]
        # s = (1, 1, 1)

        conv_block += [nn.Conv3d(dim, dim, kernel_size=kw, padding=p, bias=use_bias),
                       norm_layer(dim),
                       nn.ReLU(True)]
        if use_dropout:
            conv_block += [nn.Dropout(0.5)]

        conv_block += [nn.Conv3d(dim, dim, kernel_size=kw, padding=p, bias=use_bias),
                       norm_layer(dim)]

        return nn.Sequential(*conv_block)

    def forward(self, x):
        try:
            out = x + self.conv_block(x)
        except:
            print("xxxxx", x.size(), "conv ", self.conv_block(x).size())
        return out


class SensorGenerator(nn.Module):
    def __init__(self, input_nc, output_nc, ngf=64, norm_layer=nn.BatchNorm2d, use_dropout=False,
                 n_blocks=6, gpu_ids=[], padding_type='reflect'):
        assert (n_blocks >= 0)
        super(SensorGenerator, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.ngf = ngf
        self.gpu_ids = gpu_ids
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm3d
        else:
            use_bias = norm_layer == nn.InstanceNorm3d

        # kw = (3, 4, 4)
        # s = (1, 2, 2)

        model = [nn.Conv3d(input_nc, ngf, kernel_size=(3, 7, 7), padding=(1, 3, 3),
                           bias=use_bias),
                 norm_layer(ngf),
                 nn.ReLU(True)]

        n_downsampling = 2
        for i in range(n_downsampling):
            mult = 2 ** i
            model += [nn.Conv3d(ngf * mult, ngf * mult * 2, kernel_size=[3, 3, 3],
                                stride=(1, 2, 2), padding=(1, 1, 1), bias=use_bias),
                      norm_layer(ngf * mult * 2),
                      nn.ReLU(True)]

        mult = 2 ** n_downsampling
        for i in range(n_blocks):
            model += [ResnetBlock_3d(ngf * mult, padding_type=padding_type, norm_layer=norm_layer,
                                     use_dropout=use_dropout, use_bias=use_bias),
                      ]
        code = model[:]

        model = []

        for i in range(n_downsampling):
            mult = 2 ** (n_downsampling - i)

            model += [nn.ConvTranspose3d(ngf * mult, int(ngf * mult / 2),
                                         kernel_size=[3, 3, 3], stride=(1, 2, 2),
                                         padding=(1, 1, 1),
                                         bias=use_bias),
                      norm_layer(int(ngf * mult / 2)),
                      nn.ReLU(True)]
        model += [nn.Conv3d(ngf, output_nc, kernel_size=[3, 7, 7], padding=(1, 3, 3)),
                  nn.Conv3d(output_nc, output_nc, kernel_size=[3, 6, 6], padding=(1, 4, 4), stride=(1, 1, 1), ), ]
        model += [nn.Tanh()]

        self.model = nn.Sequential(*model)

        self.code = nn.Sequential(*code)

    def build_pre(self, code_size, out_size):
        if getattr(self, "set_pre", None):
            return
        print("set up action prediction net")

        pre = []
        pre += [
            nn.Linear(code_size, 256),
            # nn.Linear(1024, 512),
            nn.Linear(256, 64),
            nn.Linear(64, out_size),
        ]
        self.pre = pre
        self.set_pre = True

    def pre_out(self, x):
        for l in self.pre:
            # print("------------------------")
            # print(l)
            # x=x.cuda()
            # print(x)
            # l.cuda()
            x = F.relu(l(x))
        return x

    def forward(self, input):
        if self.gpu_ids and isinstance(input.data, torch.cuda.FloatTensor):
            out_size = input.size()[2]
            # input=input.cuda()
            code = self.code(input)  # .cuda()
            code = nn.parallel.data_parallel(self.code, input, self.gpu_ids)
            midvidencoder = code

            # print("code")
            # print(code)

            def mul(code):
                res = 1
                for i in code.size()[1:]:
                    res *= i
                return res

            code_size = mul(code)

            self.build_pre(code_size, out_size)

            # nn.parallel.data_parallel(self.model, code, self.gpu_ids)
            # nn.parallel.data_parallel(self.pre_out, code.view(-1, code_size), self.gpu_ids)

            return nn.parallel.data_parallel(self.model, midvidencoder, self.gpu_ids), nn.parallel.data_parallel(
                self.pre_out,
                code.view(-1,
                          code_size),
                self.gpu_ids)
        else:
            out_size = input.size()[2]
            code = self.code(input)

            def mul(code):
                res = 1
                for i in code.size()[1:]:
                    res *= i
                return res

            code_size = mul(code)

            self.build_pre(code_size, out_size)

            a = self.model(code)
            code = code.view(-1, code_size)
            b = self.pre_out(code)

            return a, b


class Action_D(nn.Module):
    def __init__(self, depth):
        super(Action_D, self).__init__()

        self.fc1 = nn.Linear(depth, 1024).cuda()
        self.fc2 = nn.Linear(1024, 256).cuda()
        self.fc3 = nn.Linear(256, 1).cuda()

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))

        return x


# Added by Jeven 2017-12-24
class ResnetVideoEncoder(nn.Module):
    def __init__(self, input_nc, output_nc, num_downs=8, ngf=64, norm_layer=nn.BatchNorm2d, target_size=1,
             use_dropout=False, n_blocks=1, gpu_ids=None, padding_type='reflect'):
        # Video encoder using part of Resnet architecture
        super(ResnetVideoEncoder, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.ngf = ngf
        self.gpu_ids = gpu_ids
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm3d
        else:
            use_bias = norm_layer == nn.InstanceNorm3d

        model = [nn.Conv3d(input_nc, ngf, kernel_size=(3, 7, 7), padding=(1, 3, 3),
                           bias=use_bias),
                 norm_layer(ngf),
                 nn.ReLU(True)]

        n_downsampling = 2
        for i in range(n_downsampling):
            mult = 2 ** i
            model += [nn.Conv3d(ngf * mult, ngf * mult * 2, kernel_size=[3, 3, 3],
                                stride=(1, 2, 2), padding=(1, 1, 1), bias=use_bias),
                      norm_layer(ngf * mult * 2),
                      nn.ReLU(True)]

        mult = 2 ** n_downsampling
        for i in range(n_blocks):
            model += [ResnetBlock_3d(ngf * mult, padding_type=padding_type, norm_layer=norm_layer,
                                     use_dropout=use_dropout, use_bias=use_bias),
                      ]
        self.model = nn.Sequential(*model)
        pass

    def forward(self, inp):
        if self.gpu_ids and isinstance(inp.data, torch.cuda.FloatTensor):
            return nn.parallel.data_parallel(self.model, inp, self.gpu_ids)
        else:
            return self.model(inp)


class ResnetVideoGenerator(nn.Module):
    """
    Video generator based on ResnetVideoEncoder
    Added by: Jeven, 2018.1.3
    """
    def __init__(self, input_nc, output_nc, ngf=64, norm_layer=nn.BatchNorm3d, use_dropout=False,
                 n_blocks=6, gpu_ids=[], padding_type='reflect'):
        assert (n_blocks >= 0)
        super(ResnetVideoGenerator, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.ngf = ngf
        self.gpu_ids = gpu_ids
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm3d
        else:
            use_bias = norm_layer == nn.InstanceNorm3d

        n_downsampling = 2
        model = []
        for i in range(n_downsampling):
            mult = 2 ** (n_downsampling - i)

            model += [nn.ConvTranspose3d(ngf * mult, int(ngf * mult / 2),
                                         kernel_size=(3, 3, 3), stride=(1, 2, 2),
                                         padding=(1, 1, 1),
                                         bias=use_bias),
                      norm_layer(int(ngf * mult / 2)),
                      nn.ReLU(True)]
        model += [nn.Conv3d(ngf, output_nc, kernel_size=(3, 7, 7), padding=(1, 3, 3)),
                  norm_layer(output_nc),
                  nn.Conv3d(output_nc, output_nc, kernel_size=(3, 6, 6), padding=(1, 4, 4), stride=(1, 1, 1))
                  ]
        model += [nn.Tanh()]
        self.model = nn.Sequential(*model)
        pass

    def forward(self, inp):
        # todo test
        if self.gpu_ids and isinstance(inp.data, torch.cuda.FloatTensor):
            return nn.parallel.data_parallel(self.model, inp, self.gpu_ids)
        else:
            return self.model(inp)


class SequenceGenerator(nn.Module):
    """
    Encoding video using a CNN image encoder (Resnet) to a sequence of embeddings,
        which are feed later into a RNN generator to generate target sequence
    inputs:
    outputs:
    """

    def __init__(self, input_nc, output_nc, num_downs=8, rnn_input_size=48576, rnn_hidden_size=80, rnn_num_layers=3,
                 rnn_bidirectional=False, ngf=64, norm_layer=nn.BatchNorm2d, target_size=1,
                 use_dropout=False, n_blocks=1, gpu_ids=None, padding_type='reflect'):
        assert (n_blocks >= 0)
        super(SequenceGenerator, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.rnn_input_size = rnn_input_size  # 194304  196608   #之前这里是  48576 不知道哪里调整后这里变大了很多。rnn参数修改后还是大5倍
        self.rnn_hidden_size = rnn_hidden_size
        self.target_size = target_size
        self.rnn_num_layers = rnn_num_layers
        self.rnn_bidirectional = rnn_bidirectional
        self.ngf = ngf
        self.gpu_ids = gpu_ids

        unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=None, norm_layer=norm_layer,
                                             innermost=True)
        for i in range(num_downs - 5):
            unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=unet_block,
                                                 norm_layer=norm_layer, use_dropout=use_dropout)
        unet_block = UnetSkipConnectionBlock(ngf * 4, ngf * 8, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(ngf * 2, ngf * 4, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(ngf, ngf * 2, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(output_nc, ngf, input_nc=input_nc, submodule=unet_block,
                                             outermost=True,
                                             norm_layer=norm_layer)

        self.video_gen = unet_block
        # Video Generator
        # self.video_gen = nn.Sequential(*model)

        # Sequence Generator
        self.rnn_generator = nn.LSTM(input_size=self.rnn_input_size, hidden_size=self.rnn_hidden_size,
                                     num_layers=self.rnn_num_layers, bidirectional=self.rnn_bidirectional,
                                     batch_first=True)
        self.rnn2out = nn.Linear(self.rnn_hidden_size, self.target_size)

    def forward(self, inp):

        input_vid = inp
        # print(input_vid)
        # if self.gpu_ids and isinstance(input_vid, torch.cuda.FloatTensor):
        # encoded_vid = nn.parallel.data_parallel(self.video_encoder, input_vid, self.gpu_ids)
        self.gen_vid = nn.parallel.data_parallel(self.video_gen, input_vid, self.gpu_ids)
        # concat real vid with gen vid, then feed to rnn
        # rnn_input = torch.cat([input_vid, self.gen_vid], dim=1)  # concat along channel dim

        ##?? input to rnn use input_A or encoded_vid????
        rnn_outs, _ = nn.parallel.data_parallel(self.rnn_generator, self.gen_vid.view(1, self.gen_vid.size()[2], -1),
                                                self.gpu_ids)
        self.gen_seq = nn.parallel.data_parallel(self.rnn2out, rnn_outs, self.gpu_ids)
        return self.gen_vid, self.gen_seq
        # else:
        #     raise NotImplementedError('cpu  data [%s] is not complete implemented')
        #     encoded_vid = self.video_encoder(input_vid)
        #     self.gen_vid = self.video_gen(encoded_vid)
        #     rnn_input = torch.cat([input_vid, self.gen_vid], dim=1)  # concat along channel dim
        #     rnn_outs, _ = self.rnn_generator(rnn_input.view(1, rnn_input.size()[2], -1))
        #     self.gen_seq = self.rnn2out(rnn_outs)
        #     return self.gen_vid, self.gen_seq

    def batch_mse_loss(self, inp, target):
        """
        Returns the MSE Loss for predicting target sequence.
        Inputs: input, target
            - input: batch_size x depth x seq_len
            - target: batch_size x depth x seq_len
            inp should be target with <s> (start letter) prepended
        """

        loss_fn = nn.MSELoss()
        self.forward(inp)
        loss = loss_fn(self.gen_seq, target)
        return loss  # per batch


class SeqCNNGenerator(nn.Module):
    """
    A conv sequence generator build on top of ResnetVideoEncoder
    Added by: Jeven, 2018.1.3
    """
    def __init__(self, input_nc, output_nc, ngf=64, norm_layer=nn.BatchNorm3d, use_dropout=False,
                 n_blocks=1, gpu_ids=[], padding_type='reflect', 
                 input_height=None, input_width=None, sequence_dim=None):
        super(SeqCNNGenerator, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.ngf = ngf
        self.gpu_ids = gpu_ids
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm3d
        else:
            use_bias = norm_layer == nn.InstanceNorm3d
        if input_height is None or input_width is None or sequence_dim is None:
            raise ValueError('Params input_height, input_width and sequence_dim is necessary.')

        n_downsampling = 2
        model = []
        mult = 2 ** n_downsampling
        model += [nn.Conv3d(ngf * mult, output_nc, kernel_size=(3, 7, 7), padding=(1, 3, 3), bias=use_bias),
                  norm_layer(output_nc),
                  nn.Conv3d(output_nc, output_nc, kernel_size=(3, 5, 5), padding=(1, 2, 2), bias=use_bias),
                  nn.Tanh()]

        self.conv = nn.Sequential(*model)

        model = [nn.Linear(output_nc * input_height * input_width, sequence_dim)] 
        if use_dropout:
            model += [nn.Dropout(p=0.5)]
        model += [nn.LeakyReLU()]
        self.output = nn.Sequential(*model)

    def forward(self, inp):
        # first conv and then reshape, feed to output
        if self.gpu_ids and isinstance(inp.data, torch.cuda.FloatTensor):
            out = nn.parallel.data_parallel(self.conv, inp, self.gpu_ids)
            return nn.parallel.data_parallel(self.output, out.view(out.size()[0], out.size()[2], -1))
        else:
            out = self.conv(inp)
            print('**', out.size())
            return self.output(out.view(out.size()[0], out.size()[2], -1))


    def batch_mse_loss(self, inp, target):
        """
        Returns the MSE Loss for predicting target sequence.
        Inputs: input, target
            - input: batch_size x depth x seq_len
            - target: batch_size x depth x seq_len
            inp should be target with <s> (start letter) prepended
        """

        loss_fn = nn.MSELoss()
        self.forward(inp)
        loss = loss_fn(self.gen_seq, target)
        return loss  # per batch


class SequenceDiscriminator(nn.Module):
    """
    Use a bidirectional LSTM as a discriminator for sequence
    inputs:
    outputs:
    """

    def __init__(self, input_size, hidden_size=200, norm_layer=nn.BatchNorm2d,
                 dropout=0.5, gpu_ids=None, num_layers=2, bidirectional=True):
        super(SequenceDiscriminator, self).__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.bidirectional = bidirectional
        self.norm_layer = num_layers
        self.dropout = dropout
        self.gpu_ids = gpu_ids

        self.rnn_discriminator = nn.LSTM(input_size=self.input_size, hidden_size=self.hidden_size,
                                         num_layers=self.num_layers, bidirectional=self.bidirectional,
                                         batch_first=True)

        output_module = [nn.Linear(2 * self.hidden_size, self.hidden_size)]  # bidirectional
        output_module += [nn.Tanh()]
        output_module += [nn.Dropout(p=dropout)]
        output_module += [nn.Linear(self.hidden_size, 1)]
        output_module += [nn.Sigmoid()]
        self.output_layer = nn.Sequential(*output_module)

    def forward(self, input):
    
        out, _ = self.rnn_discriminator(input)  # batch_size x depth(seq_len) x hidden_size
        return self.output_layer(out)

    def batch_classify(self, input):
        """
        Classifies a batch of sequences.
        Inputs: inp
            - inp: batch_size x depth(seq_len) x 2*hidden_size
        Returns: out
            - out: batch_size ([0,1] score)
        """
        out = self.forward(input)
        return out.view(out.size()[0], -1)

    def batch_bce_loss(self, input, target):
        """
        Returns Binary Cross Entropy Loss for discriminator.
         Inputs: input, target
            - input: batch_size x depth x 2*hidden_size
            - target: batch_size x depth (binary 1/0)
        """
        loss_fn = nn.BCELoss().cuda()
        out = self.batch_classify(input)
        return loss_fn(out, target)

"""
Use a CNN as a discriminator for sequence
inputs: target sequential sensor data (batch, depth, dim)
outputs: prob of being true (0, 1)
params: input_depth - the length of the input sequence;
        input_dim - dimension of input sequence
"""
class SeqCNNDiscriminator(nn.Module):
    def __init__(self, input_depth, input_dim, ndf=64, norm_layer=nn.BatchNorm3d,
                 use_dropout=False, use_sigmoid=True, gpu_ids=None):
        super(SeqCNNDiscriminator, self).__init__()
        self.gpu_ids = gpu_ids
        if type(norm_layer) == functools.partial:
            use_bias = norm_layer.func == nn.InstanceNorm2d
        else:
            use_bias = norm_layer == nn.InstanceNorm2d

        conv_module = [nn.Conv2d(in_channels=1, out_channels=ndf, kernel_size=(2, input_dim),bias=use_bias),
                       norm_layer(ndf),
                       nn.ReLU()]

        conv_module += [nn.Conv2d(in_channels=ndf, out_channels=ndf * 2, kernel_size=(2, input_dim),bias=use_bias),
                       norm_layer(ndf*2),
                       nn.ReLU()]

        self.conv_module = nn.Sequential(*conv_module)

        # reshape and feed to fcn
        output_module = [nn.Linear(2 * ndf * (input_depth - 2) * input_dim, 100)]
        output_module += [nn.ReLU()]
        if use_dropout:
            output_module += [nn.Dropout(p=0.5)]
        output_module += [nn.Linear(100, 1)]
        output_module += [nn.Sigmoid()]
        self.output_module = nn.Sequential(*output_module)

    def forward(self, inp):
        """
        :param inp: sensor sequence data with shape (batch, depth, dim)
        :return:
        """
        if self.gpu_ids and isinstance(inp.data, torch.cuda.FloatTensor):
            out = nn.parallel.data_parallel(self.conv_module,
                                            inp.view(inp.size()[0], 1, inp.size()[1], inp.size()[2]),
                                            self.gpu_ids)
            return nn.parallel.data_parallel(self.output_module, out.view(out.size()[0], -1), self.gpu_ids)
        else:
            out = self.conv_module(inp.view(inp.size()[0], 1, inp.size()[1], inp.size()[2]))
            return self.output_module(out.view(out.size()[0], -1))

    def batch_classify(self, input):
        """
        Classifies a batch of sequences.
        Inputs: inp
            - inp: batch_size x depth(seq_len) x dim
        Returns: out
            - out: batch_size ([0,1] score)
        """
        out = self.forward(input)
        return out.view(out.size()[0], -1)

    def batch_bce_loss(self, input, target):
        """
        Returns Binary Cross Entropy Loss for discriminator.
         Inputs: input, target
            - input: batch_size x depth x dim
            - target: batch_size x depth (binary 1/0)
        """
        if self.gpu_ids:
            loss_fn = nn.BCELoss().cuda()
        loss_fn = nn.BCELoss()
        out = self.batch_classify(input)
        return loss_fn(out, target)



# test
if __name__ == '__main__':
    netE = ResnetVideoEncoder(input_nc=3, output_nc=None)
    netG_vid = ResnetVideoGenerator(input_nc=None, output_nc=3)
    netG_seq = SeqCNNGenerator(input_nc=None, output_nc=3, input_height=5, input_width=5, sequence_dim=1)
    netD_seq = SeqCNNDiscriminator(input_depth=10, input_dim=1)
    input_vid = torch.autograd.Variable(torch.randn(1, 3, 10, 20, 20))
    input_seq = torch.autograd.Variable(torch.randn(1, 10, 1))

    encoded_vid = netE(input_vid)
    print('vid encoded: ', encoded_vid.size())
    gen_vid = netG_vid(encoded_vid)
    print('generated vid: ', gen_vid.size())
    gen_seq = netG_seq(encoded_vid)
    print('generated seq: ', gen_seq.size())
    pred_seq = netD_seq(gen_seq)
    print(pred_seq)

    
