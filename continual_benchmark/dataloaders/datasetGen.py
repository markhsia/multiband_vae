import torch

from random import shuffle

from torch.utils.data import Subset

from .wrapper import Subclass, AppendName, Permutation


def SplitGen(train_dataset, val_dataset, first_split_sz=2, other_split_sz=2, rand_split=False, remap_class=True,
             random_split=False):
    '''
    Generate the dataset splits based on the labels.
    :param train_dataset: (torch.utils.data.dataset)
    :param val_dataset: (torch.utils.data.dataset)
    :param first_split_sz: (int)
    :param other_split_sz: (int)
    :param rand_split: (bool) Randomize the set of label in each split
    :param remap_class: (bool) Ex: remap classes in a split from [2,4,6 ...] to [0,1,2 ...]
    :return: train_loaders {task_name:loader}, val_loaders {task_name:loader}, out_dim {task_name:num_classes}
    '''
    assert train_dataset.number_classes == val_dataset.number_classes, 'Train/Val has different number of classes'
    num_classes = train_dataset.number_classes

    # Calculate the boundary index of classes for splits
    # Ex: [0,2,4,6,8,10] or [0,50,60,70,80,90,100]
    split_boundaries = [0, first_split_sz]
    while split_boundaries[-1] < num_classes:
        split_boundaries.append(split_boundaries[-1] + other_split_sz)
    print('split_boundaries:', split_boundaries)
    assert split_boundaries[-1] == num_classes, 'Invalid split size'

    # Assign classes to each splits
    # Create the dict: {split_name1:[2,6,7], split_name2:[0,3,9], ...}
    if not rand_split:
        class_lists = {i: list(range(split_boundaries[i], split_boundaries[i + 1])) for i in
                       range(len(split_boundaries) - 1)}
    else:
        randseq = torch.randperm(num_classes)
        class_lists = {i: randseq[list(range(split_boundaries[i], split_boundaries[i + 1]))].tolist() for i in
                       range(len(split_boundaries) - 1)}
    print(class_lists)

    # Generate the dicts of splits
    # Ex: {split_name1:dataset_split1, split_name2:dataset_split2, ...}
    train_dataset_splits = {}
    val_dataset_splits = {}
    task_output_space = {}

    if random_split:
        batch_indices = (torch.rand(len(train_dataset)) * len(split_boundaries)).long()
        batch_indices = batch_indices.long()
        dataset_len = len(train_dataset)
        train_set_len = int(dataset_len * 0.8)
        train_indices = batch_indices[:train_set_len]
        val_indices = batch_indices[train_set_len:]

        for name, _ in class_lists.items():
            train_subset = Subset(train_dataset, torch.where(train_indices == name)[0])
            # train_subset.labels = train_class_indices[train_indices == name]  # torch.ones(len(train_subset), 1) * name
            # train_subset.attr = train_subset.labels
            train_subset.class_list = range(train_dataset.number_classes)

            val_subset = Subset(train_dataset, train_set_len + torch.where(val_indices == name)[0])
            # val_subset.labels = val_class_indices[val_indices == name]  # torch.ones(len(val_subset), 1) * name
            val_subset.class_list = range(train_dataset.number_classes)
            # val_subset.attr = val_subset.labels

            train_dataset_splits[name] = AppendName(train_subset, name)
            val_dataset_splits[name] = AppendName(val_subset, name)
            task_output_space[name] = (batch_indices == name).sum()
    else:
        for name, class_list in class_lists.items():
            train_dataset_splits[name] = AppendName(Subclass(train_dataset, class_list, remap_class), name)
            val_dataset_splits[name] = AppendName(Subclass(val_dataset, class_list, remap_class), name)
            task_output_space[name] = len(class_list)

    return train_dataset_splits, val_dataset_splits, task_output_space


def data_split(dataset, dataset_name, num_batches=5, num_classes=10, random_split=False, random_mini_shuffle=False,
               limit_data=None):
    if dataset_name.lower() == "celeba":
        attr = dataset.attr

        if num_classes == 10:
            class_split = {
                0: [8, 20],  # Black hair
                1: [8, -20],
                2: [11, 20],  # Brown hair
                3: [11, -20],
                4: [35, 20],  # hat man
                5: [35, -20],
                6: [9, 20],  # Blond hair
                7: [9, -20],
                8: [17],  # gray
                9: [4]  # bold
            }
        else:
            raise NotImplementedError
    else:
        split_boundaries = [0, num_classes // num_batches]
        while split_boundaries[-1] < num_classes:
            split_boundaries.append(split_boundaries[-1] + num_classes // num_batches)
        class_split = {i: list(range(split_boundaries[i], split_boundaries[i + 1])) for i in
                       range(len(split_boundaries) - 1)}

    if num_batches == 5:
        batch_split = {
            0: [0, 1],
            1: [2, 3],
            2: [4, 5],
            3: [6, 7],
            4: [8, 9]
        }
    elif num_batches == 1:
        batch_split = {
            0: range(10)
        }
    else:
        raise NotImplementedError()

    class_indices = torch.zeros(len(dataset)) - 1

    if dataset_name.lower() == "celeba":
        for class_id in class_split:
            tmp_attr = class_split[class_id]
            tmp_indices = torch.ones(len(dataset))
            for i in tmp_attr:
                if i > 0:
                    tmp_indices = tmp_indices * attr[:, i]
                else:
                    tmp_indices = tmp_indices * (1 - attr[:, -i])
            class_indices[tmp_indices.bool()] = class_id
    else:
        class_indices = torch.LongTensor(dataset.labels)

    if num_batches == 1:
        class_indices = (
                                class_indices - class_indices % 2) // 2  # To have the same classes as batch indices in normal setup
    # val_indices = torch.zeros(len(train_dataset)) - 1
    batch_indices = (torch.zeros(len(dataset)) - 2)
    if random_split:
        # batch_indices += (torch.rand_like(batch_indices) * num_batches).long()
        # to include only selected classes
        for task in batch_split:
            split = batch_split[task]
            batch_indices[(class_indices[..., None] == torch.tensor(split)).any(-1)] = (torch.rand_like(
                batch_indices[(class_indices[..., None] == torch.tensor(split)).any(-1)]) * num_batches)
        batch_indices = batch_indices.long()
    else:
        for task in batch_split:
            split = batch_split[task]
            batch_indices[(class_indices[..., None] == torch.tensor(split)).any(-1)] = task  # class_indices in split
            if random_mini_shuffle:
                if task % 2 == 0:
                    selected_indices = batch_indices[batch_indices == task]
                    random_subset = torch.rand(len(selected_indices))
                    # shuffle_size = #int(0.6 * len(selected_indices))
                    selected_indices[random_subset > 0.6] += 1
                    batch_indices[batch_indices == task] = selected_indices

    # if random_mini_shuffle:
    #     shuffle_size = int(0.5 * len(batch_indices))
    #     selected_batch_indices = batch_indices[batch_indices >= 0]
    #     selected_batch_indices[:shuffle_size] = (selected_batch_indices[:shuffle_size] + 1) % num_batches
    #     batch_indices[
    #         batch_indices >= 0] = selected_batch_indices  # = (batch_indices[batch_indices >= 0][:shuffle_size] + 1) % num_batches
    dataset.attr = class_indices.view(-1, 1).long()

    train_dataset_splits = {}
    val_dataset_splits = {}
    task_output_space = {}

    dataset_len = len(dataset)
    train_set_len = int(dataset_len * 0.8)
    train_indices = batch_indices[:train_set_len]
    train_class_indices = class_indices[:train_set_len]
    val_indices = batch_indices[train_set_len:]
    val_class_indices = class_indices[train_set_len:]

    for name in batch_split:
        current_batch_indices = torch.where(train_indices == name)[0]
        if limit_data:
            random_subset = torch.rand(len(current_batch_indices))
            current_batch_indices = current_batch_indices[random_subset > 1 - limit_data]
        train_subset = Subset(dataset, current_batch_indices)
        if dataset_name.lower() == "celeba":
            train_subset.labels = train_class_indices[current_batch_indices]  # torch.ones(len(train_subset), 1) * name
        # train_subset.attr = train_subset.labels
        train_subset.class_list = batch_split[name]

        val_subset = Subset(dataset, train_set_len + torch.where(val_indices == name)[0])
        if dataset_name.lower() == "celeba":
            val_subset.labels = val_class_indices[val_indices == name]  # torch.ones(len(val_subset), 1) * name
        val_subset.class_list = batch_split[name]
        # val_subset.attr = val_subset.labels

        train_dataset_splits[name] = AppendName(train_subset, name)
        val_dataset_splits[name] = AppendName(val_subset, name)
        task_output_space[name] = (batch_indices == name).sum()

    print(f"Prepared dataset with splits: {[(idx,len(data)) for idx,data in enumerate(train_dataset_splits.values())]}")


    return train_dataset_splits, val_dataset_splits, task_output_space


def PermutedGen(train_dataset, val_dataset, n_permute, remap_class=False):
    sample, _ = train_dataset[0]
    n = sample.numel()
    train_datasets = {}
    val_datasets = {}
    task_output_space = {}
    for i in range(1, n_permute + 1):
        rand_ind = list(range(n))
        shuffle(rand_ind)
        name = str(i)
        first_class_ind = (i - 1) * train_dataset.number_classes if remap_class else 0
        train_datasets[name] = AppendName(Permutation(train_dataset, rand_ind), name, first_class_ind=first_class_ind)
        val_datasets[name] = AppendName(Permutation(val_dataset, rand_ind), name, first_class_ind=first_class_ind)
        task_output_space[name] = train_dataset.number_classes
    return train_datasets, val_datasets, task_output_space
