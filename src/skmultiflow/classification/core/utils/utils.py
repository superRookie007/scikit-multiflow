def do_naive_bayes_prediction(X, observed_class_distribution: dict, attribute_observers: dict):
    if observed_class_distribution == {}:
        # No observed class distributions, all target_values equal
        return {0: 0.0}
    votes = {}
    observed_class_sum = sum(observed_class_distribution.values())
    for class_index, observed_class_val in observed_class_distribution.items():
        votes[class_index] = observed_class_val / observed_class_sum
        if attribute_observers:
            for att_idx in range(len(X)):
                if att_idx in attribute_observers:
                    obs = attribute_observers[att_idx]
                    votes[class_index] *= obs.probability_of_attribute_value_given_class(X[att_idx], class_index)
    return votes
