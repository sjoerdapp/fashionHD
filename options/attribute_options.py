from base_options import BaseOptions

class BaseAttributeOptions(BaseOptions):

    def initialize(self):
        super(BaseAttributeOptions, self).initialize()
        parser = self.parser

        # basic options
        parser.add_argument('--n_attr', type = int, default = 1000, help = 'number of attribute entries')
        parser.add_argument('--input_nc', type = int, default = 3, help = 'channel number of input images')
        parser.add_argument('--spatial_pool', type = str, default = 'none', help = 'spatial pooling method [max|noisy-or]',
            choices = ['max', 'noisyor', 'none'])
        parser.add_argument('--convnet', type = str, default = 'resnet18', help = 'CNN architecture [resnetX]')
        parser.add_argument('--feat_norm', default = False, action = 'store_true', help = 'Normalize feature using L2 norm')
        parser.add_argument('--balanced', default = False, action = 'store_true', help = 'balanced loss weight for positive and negative samples')
        # parser.add_argument('--loss_weight', type = float, default = 1.0, help = 'loss multiplier coefficient')
        parser.add_argument('--loss_type', type = str, default = 'bce', help = '[bce|wbce] bce: use torch.nn.BCELoss(); wbce: use models.network.WeightBCELoss()', 
            choices = ['bce', 'wbce'])
        parser.add_argument('--wbce_class_norm', default = False, action = 'store_true', help = 'when using WeightBCELoss, normalize loss within each class by the sum of weights.')
        parser.add_argument('--no_size_avg', default = False, action = 'store_true', help = 'do not average loss over observations')

        parser.add_argument('--joint_cat', default = False, action = 'store_true', help = 'joint traing attribute encoder with category classfication task')
        parser.add_argument('--n_cat', type = int, default = 50, help = 'number of cloth categories for joint learning')
        parser.add_argument('--cat_loss_weight', type = float, default = 1e-2, help = 'loss weight of category classification loss')

        parser.add_argument('--input_lm', default = False, action = 'store_true', help = 'use landmark heatmap input')
        parser.add_argument('--lm_input_nc', type = int, default = 18, help = 'landmark number')
        parser.add_argument('--lm_output_nc', type = int, default = 128, help = 'landmark branch output feature channels')
        parser.add_argument('--lm_fusion', type = str, default = 'concat', help = 'fusion method of RGB channel and landmark channel [concat|channel]',
            choices = ['concat', 'linear'])

        # data files
        # refer to "scripts/preproc_inshop.py" for more information
        parser.add_argument('--benchmark', type = str, default = 'ca', help = 'set benchmark [ca|ca_org|inshop|user|debug]',
            choices = ['ca', 'ca_color', 'inshop', 'debug', 'user', 'ca_org'])
        parser.add_argument('--fn_sample', type = str, default = 'default', help = 'path of sample index file')
        parser.add_argument('--fn_label', type = str, default = 'default', help = 'path of attribute label file')
        parser.add_argument('--fn_entry', type = str, default = 'default', help = 'path of attribute entry file')
        parser.add_argument('--fn_split', type = str, default = 'default', help = 'path of split file')
        parser.add_argument('--fn_landmark', type = str, default = 'default', help = 'path of landmark label file')
        parser.add_argument('--fn_cat', type = str, default = 'default', help = 'path of category label file')
        parser.add_argument('--unmatch', default = False, action = 'store_true', help = 'use unmatched training sample and label for debug')
        # misc
        parser.add_argument('--batch_size', type = int, default = 128, help = 'batch size')
        self.parser.add_argument('--pavi', default = False, action = 'store_true', help = 'activate pavi log')

    def auto_set(self):
        super(BaseAttributeOptions, self).auto_set()

        opt = self.opt
        ###########################################
        # Add id profix
        if not opt.id.startswith('AE_'):
            opt.id = 'AE_' + opt.id


        ###########################################
        # Set default dataset file pathes
        if opt.benchmark == 'ca':
            if opt.fn_sample == 'default':
                opt.fn_sample = 'Label/ca_samples.json'
            if opt.fn_label == 'default':
                opt.fn_label = 'Label/ca_attr_label.pkl'
            if opt.fn_entry == 'default':
                opt.fn_entry = 'Label/attr_entry.json'
            if opt.fn_split == 'default':
                opt.fn_split = 'Split/ca_split_trainval.json'
            if opt.fn_landmark == 'default':
                opt.fn_landmark = 'Label/ca_landmark_label_256.pkl'
            if opt.fn_cat == 'default':
                opt.fn_cat = 'Label/ca_cat_label.pkl'

        elif opt.benchmark == 'ca_color':
            if opt.fn_sample == 'default':
                opt.fn_sample = 'Label/ca_samples.json'
            if opt.fn_label == 'default':
                opt.fn_label = 'Label/ca_color_attr_label.pkl'
            if opt.fn_entry == 'default':
                opt.fn_entry = 'Label/color_attr_entry.json'
            if opt.fn_split == 'default':
                opt.fn_split = 'Split/ca_split_trainval.json'
            if opt.fn_landmark == 'default':
                opt.fn_landmark = 'Label/ca_landmark_label_256.pkl'
            if opt.fn_cat == 'default':
                opt.fn_cat = 'Label/ca_cat_label.pkl'
            opt.n_attr = 604

        elif opt.benchmark == 'ca_org':
            if opt.fn_sample == 'default':
                opt.fn_sample = 'Label/ca_samples_org.json'
            if opt.fn_label == 'default':
                opt.fn_label = 'Label/ca_attr_label.pkl'
            if opt.fn_entry == 'default':
                opt.fn_entry = 'Label/attr_entry.json'
            if opt.fn_split == 'default':
                opt.fn_split = 'Split/ca_split_trainval.json'
            if opt.fn_landmark == 'default':
                opt.fn_landmark = 'Label/ca_landmark_label.pkl'
            if opt.fn_cat == 'default':
                opt.fn_cat = 'Label/ca_cat_label.pkl'

        elif opt.benchmark == 'inshop':
            if opt.fn_sample == 'default':
                opt.fn_sample = 'Label/inshop_samples.json'
            if opt.fn_label == 'default':
                opt.fn_label = 'Label/inshop_attr_label.pkl'
            if opt.fn_entry == 'default':
                opt.fn_entry = 'Label/attr_entry.json'
            if opt.fn_split == 'default':
                opt.fn_split = 'Split/inshop_split.json'
            if opt.fn_landmark == 'default':
                opt.fn_landmark = 'Label/inshop_landmark_label_256.pkl'

        elif opt.benchmark == 'debug':
            opt.fn_sample = 'Label/debugca_samples.json'
            opt.fn_label = 'Label/debugca_attr_label.pkl'
            opt.fn_entry = 'Label/attr_entry.json'
            opt.fn_split = 'Split/debugca_split.json'
            opt.fn_landmark = 'Label/debugca_landmark_label.pkl'
            opt.fn_cat = 'Label/ca_cat_label.pkl'

        ###########################################
        # Set dataset mode
        if opt.input_lm:
            opt.dataset_mode = 'attribute_exp'
        else:
            opt.dataset_mode = 'attribute'



class TrainAttributeOptions(BaseAttributeOptions):

    def initialize(self):

        super(TrainAttributeOptions, self).initialize()
        parser = self.parser
        
        # train
        parser.add_argument('--continue_train', action = 'store_true', default = False, help = 'coninue training from saved model')
        
        # optimizer (we use Adam)
        parser.add_argument('--optim', type = str, default = 'adam', help = 'optimizer type [adam|sgd]', 
            choices = ['adam', 'sgd'])
        parser.add_argument('--lr', type = float, default = 1e-3, help = 'initial learning rate')
        parser.add_argument('--beta1', type = float, default = 0.9, help = 'momentum term for Adam')
        parser.add_argument('--weight_decay', type = float, default = 0, help = 'weight decay')
        

        # scheduler
        self.parser.add_argument('--lr_policy', type=str, default='step', help='learning rate policy: lambda|step|plateau',
            choices = ['step', 'plateau', 'lambda'])
        self.parser.add_argument('--epoch_count', type=int, default=1, help='the starting epoch count, we save the model by <epoch_count>, <epoch_count>+<save_latest_freq>, ...')
        self.parser.add_argument('--niter', type = int, default = 30, help = '# of iter at starting learning rate')
        self.parser.add_argument('--niter_decay', type=int, default=0, help='# of iter to linearly decay learning rate to zero')
        self.parser.add_argument('--lr_decay', type=int, default=10, help='multiply by a gamma every lr_decay_interval epochs')
        self.parser.add_argument('--lr_gamma', type = float, default = 0.1, help='lr decay rate')

        self.parser.add_argument('--display_freq', type = int, default = 10, help='frequency of showing training results on screen')
        self.parser.add_argument('--test_epoch_freq', type = int, default = 5, help='frequency of testing model')
        self.parser.add_argument('--save_epoch_freq', type = int, default = 5, help='frequency of saving model to disk' )

        # set train
        self.is_train = True

class TestAttributeOptions(BaseAttributeOptions):

    def initialize(self):

        super(TestAttributeOptions, self).initialize()

        # test

        # set test
        self.is_train = False

